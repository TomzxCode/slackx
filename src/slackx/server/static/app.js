/* slackx web UI.
 *
 * A single-file Vue 3 application (no build step, Vue loaded from CDN):
 * sidebar with channels and people, a Slack-like message list, a thread
 * panel, and a Ctrl+P palette for jumping between channels and messages.
 * Views are routed through Slack-style /archives/... URLs (mirroring
 * slackx/urls.py) so any channel or thread can be linked and the
 * browser back/forward buttons work. The HTML template lives in
 * index.html; this file holds state and logic.
 */
(function () {
  'use strict';

  if (!window.Vue) {
    return; // index.html already surfaced the CDN failure message.
  }

  // The app restores the viewport itself, from a permalink target or a
  // stored position. Letting the browser restore a scroll offset as well
  // would pull the view to wherever the reader was last (typically the end
  // of the channel) on a reload or back/forward navigation.
  if (window.history && 'scrollRestoration' in window.history) {
    window.history.scrollRestoration = 'manual';
  }

  // ------------------------------------------------------------- helpers

  function escapeHtml(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function escapeRegExp(s) {
    return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  }

  function initials(name) {
    var parts = String(name || '?').trim().split(/\s+/).filter(function (p) {
      return /^[a-z0-9]/i.test(p);
    });
    if (!parts.length) return '?';
    if (parts.length === 1) return parts[0].slice(0, 2);
    return parts[0][0] + parts[parts.length - 1][0];
  }

  function colorFor(id) {
    var hash = 0;
    var s = String(id || '');
    for (var i = 0; i < s.length; i++) hash = (hash * 31 + s.charCodeAt(i)) >>> 0;
    return 'hsl(' + (hash % 360) + ', 45%, 42%)';
  }

  function tsToDate(ts) {
    var f = parseFloat(ts);
    return isNaN(f) ? null : new Date(f * 1000);
  }

  function sameDay(a, b) {
    return a && b && a.getFullYear() === b.getFullYear() &&
      a.getMonth() === b.getMonth() && a.getDate() === b.getDate();
  }

  var MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July',
    'August', 'September', 'October', 'November', 'December'];

  function dayLabel(date) {
    if (!date) return '';
    var now = new Date();
    var yesterday = new Date(now.getTime() - 86400000);
    if (sameDay(date, now)) return 'Today';
    if (sameDay(date, yesterday)) return 'Yesterday';
    return MONTHS[date.getMonth()] + ' ' + date.getDate() + ', ' + date.getFullYear();
  }

  function fmtTime(date) {
    if (!date) return '';
    var h = date.getHours();
    var m = String(date.getMinutes()).padStart(2, '0');
    var ampm = h >= 12 ? 'PM' : 'AM';
    h = h % 12 || 12;
    return h + ':' + m + ' ' + ampm;
  }

  function fmtRelative(ts) {
    var date = tsToDate(ts);
    if (!date) return '';
    var diff = (Date.now() - date.getTime()) / 1000;
    if (diff < 90) return 'now';
    if (diff < 3600) return Math.round(diff / 60) + 'm';
    if (diff < 86400) return Math.round(diff / 3600) + 'h';
    if (diff < 86400 * 14) return Math.round(diff / 86400) + 'd';
    return dayLabel(date);
  }

  function groupByDay(messages) {
    var groups = [];
    var current = null;
    messages.forEach(function (m) {
      var date = tsToDate(m.ts);
      if (!current || !sameDay(current.date, date)) {
        current = { date: date, label: dayLabel(date), messages: [] };
        groups.push(current);
      }
      current.messages.push(m);
    });
    return groups;
  }

  // Highlight each query term (prefix match) inside already-escaped text.
  // Returns HTML using <mark>; input must be raw text.
  function highlightTerms(rawText, query) {
    var safe = escapeHtml(rawText);
    String(query || '').trim().split(/\s+/).forEach(function (term) {
      if (!term) return;
      var re = new RegExp('(' + escapeRegExp(escapeHtml(term)) + '\\w*)', 'gi');
      safe = safe.replace(re, '\u0001$1\u0002');
    });
    return safe.split('\u0001').join('<mark>').split('\u0002').join('</mark>');
  }

  // The server snippet wraps matches in [ ]; convert to <mark>.
  function markedSnippet(snippet) {
    return escapeHtml(snippet || '')
      .replace(/\[/g, '<mark>')
      .replace(/\]/g, '</mark>');
  }

  // Convert raw mrkdwn text into safe HTML. ``ctx`` supplies
  // {userNames, channelsById} for mention resolution.
  function mrkdwnToHtml(rawText, ctx) {
    var codes = [];
    var stash = function (html) {
      codes.push(html);
      return '\u0000' + (codes.length - 1) + '\u0000';
    };

    var s = escapeHtml(rawText);

    // Fenced and inline code first, protected from the other rules.
    s = s.replace(/```([\s\S]*?)```/g, function (_, code) {
      return stash('<pre><code>' + code.replace(/^\n+|\n+$/g, '') + '</code></pre>');
    });
    s = s.replace(/`([^`\n]+)`/g, function (_, code) {
      return stash('<code>' + code + '</code>');
    });

    // Links: <url|label> then bare <url>.
    s = s.replace(/&lt;(https?:\/\/[^|&\s]+)\|([^&]+?)&gt;/g, function (_, url, label) {
      return '<a href="' + url + '" target="_blank" rel="noopener noreferrer">' + label + '</a>';
    });
    s = s.replace(/&lt;(https?:\/\/[^|&\s]+)&gt;/g, function (_, url) {
      return '<a href="' + url + '" target="_blank" rel="noopener noreferrer">' + url + '</a>';
    });

    // User mentions <@U123|label>.
    s = s.replace(/&lt;@(U[A-Z0-9]+)(?:\|([^&]*))?&gt;/g, function (_, uid, label) {
      var name = ctx.userNames[uid] || label || uid;
      return '<span class="mention">@' + escapeHtml(name) + '</span>';
    });

    // Channel mentions <#C123|name>.
    s = s.replace(/&lt;#(C[A-Z0-9]+)(?:\|([^&]*))?&gt;/g, function (_, cid, label) {
      var chan = ctx.channelsById[cid];
      var name = label || (chan && (chan.display_name || chan.name)) || cid;
      return '<span class="mention channel-mention" data-channel="' + cid + '">#' +
        escapeHtml(name) + '</span>';
    });

    // Special mentions <!here> <!channel> <!everyone> and <!date^...|label>.
    s = s.replace(/&lt;!(here|channel|everyone)&gt;/g, function (_, w) {
      return '<span class="mention">@' + w + '</span>';
    });
    s = s.replace(/&lt;!date\^[^&]*\|([^&]+)&gt;/g, '$1');

    // Styling.
    s = s.replace(/\*([^*\n]+)\*/g, '<strong>$1</strong>');
    s = s.replace(/(^|[\s(])_([^_\n]+)_(?=$|[\s).,!?;:])/g, '$1<em>$2</em>');
    s = s.replace(/(^|[\s(])~([^~\n]+)~(?=$|[\s).,!?;:])/g, '$1<del>$2</del>');

    // Restore protected code segments.
    s = s.replace(/\u0000(\d+)\u0000/g, function (_, i) { return codes[+i]; });
    return s;
  }

  // A block text object ({type: 'mrkdwn'|'plain_text', text}).
  function textObjectHtml(obj, ctx) {
    if (!obj || obj.text == null) return '';
    return obj.type === 'plain_text' ? escapeHtml(obj.text) : mrkdwnToHtml(obj.text, ctx);
  }

  // Render Slack layout blocks into HTML. Bot messages (GitHub, Jira, ...)
  // usually carry their links only inside blocks; the raw ``text`` field is
  // then just a plain fallback without markup.
  function renderBlocksHtml(blocks, ctx) {
    var out = [];
    (blocks || []).forEach(function (b) {
      if (!b) return;
      if (b.type === 'section') {
        if (b.text) out.push('<div class="block">' + textObjectHtml(b.text, ctx) + '</div>');
        (b.fields || []).forEach(function (f) {
          out.push('<div class="block">' + textObjectHtml(f, ctx) + '</div>');
        });
      } else if (b.type === 'header') {
        out.push('<div class="block block-header">' + textObjectHtml(b.text, ctx) + '</div>');
      } else if (b.type === 'divider') {
        out.push('<hr class="block-divider">');
      } else if (b.type === 'context') {
        var parts = (b.elements || []).map(function (e) {
          return (e && (e.type === 'plain_text' || e.type === 'mrkdwn'))
            ? textObjectHtml(e, ctx) : '';
        }).filter(function (p) { return p; });
        if (parts.length) {
          out.push('<div class="block block-context">' + parts.join(' ') + '</div>');
        }
      } else if (b.type === 'actions') {
        (b.elements || []).forEach(function (e) {
          if (e && e.type === 'button' && e.url) {
            var label = (e.text && e.text.text) || e.url;
            out.push('<a class="block-btn" href="' + escapeHtml(e.url) +
              '" target="_blank" rel="noopener noreferrer">' + escapeHtml(label) + '</a>');
          }
        });
      }
    });
    return out.join('');
  }

  // Older-style attachments: linked title plus mrkdwn body text.
  function renderAttachmentsHtml(attachments, ctx) {
    var out = [];
    (attachments || []).forEach(function (a) {
      if (!a) return;
      var parts = [];
      if (a.title) {
        parts.push(a.title_link
          ? '<a href="' + escapeHtml(a.title_link) + '" target="_blank" rel="noopener noreferrer">' +
            escapeHtml(a.title) + '</a>'
          : escapeHtml(a.title));
      }
      if (a.text) parts.push(mrkdwnToHtml(a.text, ctx));
      if (parts.length) out.push('<div class="attachment">' + parts.join('<br>') + '</div>');
    });
    return out.join('');
  }

  // Render a message body: blocks when present (their markup carries the
  // links), otherwise the mrkdwn ``text`` fallback; attachments append below.
  function renderMessageHtml(msg, ctx) {
    var payload = msg.payload || {};
    var html = renderBlocksHtml(payload.blocks, ctx);
    if (!html && msg.text) html = mrkdwnToHtml(msg.text, ctx);
    html += renderAttachmentsHtml(payload.attachments, ctx);
    return html;
  }

  // The reader name the web UI stores its viewed positions under. Read
  // markers are namespaced by reader, so this stays separate from the
  // positions the CLI or other consumers keep over the same cache.
  var WEB_UI_READER = 'web-ui';

  // Wait this long after the last scroll event before saving a position, so
  // a fast scroll sends one write instead of one per frame.
  var POSITION_SAVE_DELAY_MS = 400;

  // Input that means the reader is scrolling, which ends an alignment.
  var USER_INPUT_EVENTS = ['wheel', 'touchstart', 'touchmove', 'keydown', 'mousedown'];

  // The top message plus where it starts relative to the viewport, so a
  // reload can put the same spot back even when the message is partly
  // scrolled above the top edge (a negative offset).
  function topVisibleAnchor(scroller) {
    if (!scroller) return null;
    var boundary = scroller.getBoundingClientRect().top;
    var rows = scroller.querySelectorAll('[data-ts]');
    for (var i = 0; i < rows.length; i++) {
      var rect = rows[i].getBoundingClientRect();
      if (rect.bottom > boundary + 1) {
        return { ts: rows[i].getAttribute('data-ts'), offset: rect.top - boundary };
      }
    }
    return null;
  }

  // The ts of the message at the top of a scroller. Any partially visible
  // top message counts, so restoring it puts the reader back at the same
  // viewport rather than at the next message below it.
  function topVisibleTs(scroller) {
    var anchor = topVisibleAnchor(scroller);
    if (anchor) return anchor.ts;
    if (!scroller) return null;
    var rows = scroller.querySelectorAll('[data-ts]');
    return rows.length ? rows[rows.length - 1].getAttribute('data-ts') : null;
  }

  // The row for ts, or the nearest following message when that exact ts is
  // no longer cached (deleted, edited away, or outside the loaded page).
  function findMessageRow(scroller, ts) {
    if (!scroller) return null;
    var rows = scroller.querySelectorAll('[data-ts]');
    var wanted = parseFloat(ts);
    var nearest = null;
    for (var i = 0; i < rows.length; i++) {
      var rowTs = rows[i].getAttribute('data-ts');
      if (rowTs === ts) return rows[i];
      if (!nearest && !isNaN(wanted) && parseFloat(rowTs) >= wanted) nearest = rows[i];
    }
    return nearest;
  }

  // How far back the automatic on-switch refresh re-reads history. Within
  // this window new messages, edits and deletions are all picked up; older
  // changes need the full "Refresh from Slack" button.
  var AUTO_REFRESH_WINDOW_DAYS = 7;

  // Themes shipped by the daisyUI CDN stylesheet (themes.css), in menu order.
  // "System" resolves to light/dark via prefers-color-scheme.
  var THEMES = [
    'system', 'light', 'dark',
    'cupcake', 'bumblebee', 'emerald', 'corporate',
    'synthwave', 'retro', 'cyberpunk', 'valentine',
    'halloween', 'garden', 'forest', 'aqua',
    'lofi', 'pastel', 'dream', 'wireframe',
    'black', 'luxury', 'dracula', 'cmyk',
    'autumn', 'business', 'acid', 'lemonade',
    'night', 'coffee', 'winter', 'dim',
    'nord', 'sunset', 'caramellatte', 'abyss', 'silk', 'fantasy',
  ];

  // ------------------------------------------------------------- routing

  // Slack-style URLs, mirroring the permalink grammar in urls.py:
  //   /                                              -> home
  //   /archives/<CHANNEL_ID>                         -> channel view
  //   /archives/<CHANNEL_ID>/p<PTS>                  -> channel, message highlighted
  //   /archives/<CHANNEL_ID>/p<PTS>?thread_ts=<TS>   -> thread panel open
  // p<PTS> is a Slack timestamp with the dot removed (p1700000000123456
  // -> 1700000000.123456). With thread_ts present the path ts is the
  // highlighted message and the query ts is the thread root, matching how
  // Slack permalink URLs mark reply links.
  var CHANNEL_PREFIXES = ['C', 'G', 'D'];
  var PTS_RE = /^p\d{7,}$/;

  function tsToPts(ts) {
    var parts = String(ts).split('.');
    return 'p' + parts[0] + ((parts[1] || '') + '000000').slice(0, 6);
  }

  function parseRoute(pathname, search) {
    var parts = pathname.split('/').filter(function (p) { return p; });
    if (!parts.length) return { channelId: null, messageTs: null, threadTs: null };
    if (parts[0] !== 'archives' || parts.length > 3) return null;
    var channel = parts[1] || '';
    if (!channel || CHANNEL_PREFIXES.indexOf(channel[0]) === -1) return null;
    var route = { channelId: channel, messageTs: null, threadTs: null };
    if (parts.length === 3) {
      if (!PTS_RE.test(parts[2])) return null;
      var digits = parts[2].slice(1);
      route.messageTs = digits.slice(0, -6) + '.' + digits.slice(-6);
    }
    var threadTs = new URLSearchParams(search || '').get('thread_ts');
    if (threadTs) route.threadTs = threadTs;
    return route;
  }

  function routeUrl(route) {
    if (!route || !route.channelId) return '/';
    var path = '/archives/' + encodeURIComponent(route.channelId);
    // The path points at the specific message when one is given; the thread
    // root only fills the path when no message ts is known (bare thread view).
    var pathTs = route.messageTs || route.threadTs;
    if (pathTs) {
      path += '/' + tsToPts(pathTs);
    }
    if (route.threadTs) {
      path += '?thread_ts=' + encodeURIComponent(route.threadTs);
    }
    return path;
  }

  // ------------------------------------------------------------- app

  var app = Vue.createApp({
    data: function () {
      return {
        booted: false,
        directoryLoaded: false,
        summary: null,
        users: [],
        channels: [],
        channelsById: {},
        userNames: {},
        userAvatars: {},

        view: 'home',            // 'home' | 'channel'
        channelId: null,
        channel: null,           // {id, name, is_private} of the open channel
        messages: [],            // thread roots, newest first
        hasMore: false,
        loadingMessages: false,
        loadingOlder: false,

        thread: null,            // {channel_id, thread_ts, messages, loading}
        highlightTs: null,

        // Viewing positions persisted as read markers under WEB_UI_READER:
        // '<channel>|<thread ts or empty>' -> top visible message ts. Dirty
        // entries wait for the debounced PUT.
        readPositions: {},
        dirtyPositions: {},
        positionTimer: null,
        readPositionsReady: null,
        readPositionsLoaded: false,

        refreshing: null,        // label of the refresh in progress
        toasts: [],
        toastSeq: 0,

        paletteOpen: false,
        paletteQuery: '',
        paletteItems: [],
        paletteActive: 0,
        paletteMsgsLoading: false,
        paletteTimer: null,
        paletteSearchSeq: 0,

        profile: null,

        theme: 'dark',
        themes: THEMES,
      };
    },

    computed: {
      messageGroups: function () {
        // The API returns roots newest-first; display oldest at the top
        // like Slack, so reverse before grouping by day.
        return groupByDay(this.messages.slice().reverse());
      },

      threadGroups: function () {
        // Thread messages arrive chronologically already.
        return this.thread ? groupByDay(this.thread.messages) : [];
      },

      recentChannels: function () {
        return this.channels
          .filter(function (c) { return c.message_count > 0; })
          .sort(function (a, b) { return (b.latest_ts || 0) - (a.latest_ts || 0); })
          .slice(0, 8);
      },

      // Identity of the routed view; changes keep the address bar in sync.
      urlKey: function () {
        return this.view === 'channel'
          ? this.channelId + '|' + (this.thread ? this.thread.thread_ts : '')
          : 'home';
      },
    },

    watch: {
      urlKey: function () { this.syncUrl(); },
    },

    methods: {
      // Expose helpers used by the in-DOM template.
      fmtRelative: fmtRelative,
      fmtTime: fmtTime,
      tsToDate: tsToDate,
      highlightTerms: highlightTerms,

      msgCtx: function () {
        return {
          userNames: this.userNames,
          channelsById: this.channelsById,
          userAvatars: this.userAvatars,
          channelId: this.channelId,
        };
      },

      // Channel messages in the thread panel link to the thread itself.
      threadCtx: function () {
        if (!this.thread) return this.msgCtx();
        return {
          userNames: this.userNames,
          channelsById: this.channelsById,
          userAvatars: this.userAvatars,
          channelId: this.thread.channel_id,
          threadTs: this.thread.thread_ts,
        };
      },

      groupTitle: function (type) {
        return type === 'channel' ? 'Channels'
          : type === 'person' ? 'People' : 'Messages';
      },

      markedSnippet: function (hit) {
        return hit.snippet ? markedSnippet(hit.snippet)
          : highlightTerms(hit.text || '', this.paletteQuery);
      },

      // -------------------------------------------------- api + toasts

      toast: function (text, kind) {
        var id = ++this.toastSeq;
        this.toasts.push({ id: id, text: text, kind: kind || '' });
        var self = this;
        setTimeout(function () {
          self.toasts = self.toasts.filter(function (t) { return t.id !== id; });
        }, 6000);
      },

      _api: function (path, opts) {
        return fetch(path, opts).then(function (res) {
          return res.json().catch(function () { return {}; }).then(function (body) {
            if (!res.ok) {
              var detail = (body && body.detail) || res.statusText;
              throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail));
            }
            return body;
          });
        });
      },

      post: function (path) { return this._api(path, { method: 'POST' }); },

      // -------------------------------------------------- boot

      boot: function () {
        var self = this;
        this.booted = true;
        this.readPositionsReady = this.loadReadPositions();
        this.applyLocation();
        this._api('/api/summary').then(function (body) {
          self.summary = body;
        }).catch(function (err) { self.toast('Failed to load summary: ' + err.message, 'error'); });
        this.loadDirectory();
      },

      loadDirectory: function () {
        var self = this;
        Promise.all([this._api('/api/users'), this._api('/api/channels')])
          .then(function (results) {
            self.users = results[0].users;
            self.channels = results[1].channels;
            var byId = {};
            self.channels.forEach(function (c) { byId[c.id] = c; });
            self.channelsById = Object.assign({}, self.channelsById, byId);
            self.rememberUsers(self.users);
            self.directoryLoaded = true;
          }).catch(function (err) {
            self.directoryLoaded = true;
            self.toast('Failed to load directory: ' + err.message, 'error');
          });
      },

      rememberUsers: function (users) {
        var names = Object.assign({}, this.userNames);
        var avatars = Object.assign({}, this.userAvatars);
        (users || []).forEach(function (u) {
          names[u.id] = u.display_name;
          avatars[u.id] = u.avatar || '';
        });
        this.userNames = names;
        this.userAvatars = avatars;
      },

      // -------------------------------------------------- viewed position

      positionKey: function (channelId, threadTs) {
        return channelId + '|' + (threadTs || '');
      },

      // Load every stored position once at boot, so opening a channel or
      // thread can restore its viewport from memory.
      loadReadPositions: function () {
        var self = this;
        return this._api('/api/read?reader=' + encodeURIComponent(WEB_UI_READER))
          .then(function (body) {
            var positions = {};
            (body.markers || []).forEach(function (marker) {
              positions[self.positionKey(marker.channel, marker.thread_ts)] =
                marker.last_read_ts;
            });
            self.readPositions = positions;
          })
          .catch(function () {
            // Best effort: without stored positions the UI opens at the
            // top of the loaded page, as it did before.
          })
          .then(function () { self.readPositionsLoaded = true; });
      },

      readPosition: function (channelId, threadTs) {
        if (!channelId) return null;
        return this.readPositions[this.positionKey(channelId, threadTs)] || null;
      },

      // Record the message now at the top of the viewport. Updating the
      // in-memory map is immediate (so a quick switch back restores the
      // right place); the PUT is debounced and flushed on navigation.
      rememberPosition: function (channelId, threadTs, ts) {
        if (!this.readPositionsLoaded || !channelId || !ts) return;
        var key = this.positionKey(channelId, threadTs);
        if (this.readPositions[key] === ts) return;
        var positions = Object.assign({}, this.readPositions);
        positions[key] = ts;
        this.readPositions = positions;
        var dirty = Object.assign({}, this.dirtyPositions);
        dirty[key] = { channel: channelId, thread_ts: threadTs || null, ts: ts };
        this.dirtyPositions = dirty;
        this.schedulePositionSave();
      },

      schedulePositionSave: function () {
        var self = this;
        if (this.positionTimer) clearTimeout(this.positionTimer);
        this.positionTimer = setTimeout(function () {
          self.positionTimer = null;
          self.flushReadPositions();
        }, POSITION_SAVE_DELAY_MS);
      },

      flushReadPositions: function () {
        if (this.positionTimer) {
          clearTimeout(this.positionTimer);
          this.positionTimer = null;
        }
        var pending = this.dirtyPositions;
        this.dirtyPositions = {};
        Object.keys(pending).forEach(function (key) {
          var p = pending[key];
          // keepalive lets the last write finish while the page unloads.
          fetch('/api/read', {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              reader: WEB_UI_READER,
              channel: p.channel,
              thread_ts: p.thread_ts,
              last_read_ts: p.ts,
            }),
            keepalive: true,
          }).catch(function () {
            // Position tracking is best effort; a failed write must not
            // interrupt reading.
          });
        });
      },

      onMessageScroll: function (e) {
        // Ignore the scroll events produced while a channel's content is
        // being replaced, or they would record the previous channel's
        // position under the channel being opened.
        if (this.loadingMessages) return;
        // While an alignment is running, scrolls come from the app itself or
        // from the browser restoring a nested scroller on reload; neither is
        // the reader moving, and the alignment keeps re-applying the target.
        if (this._aligning && this._aligning.msgScroll) return;
        this.rememberPosition(this.channelId, null, topVisibleTs(e.target));
      },

      onThreadScroll: function (e) {
        if (!this.thread || this.thread.loading) return;
        if (this._aligning && this._aligning.threadScroll) return;
        this.rememberPosition(
          this.thread.channel_id, this.thread.thread_ts, topVisibleTs(e.target));
      },

      // A real scroll by the reader (wheel, trackpad, touch, keys, or a
      // scrollbar drag) ends any alignment so it stops fighting them.
      cancelAlignment: function () {
        var aligning = this._aligning || {};
        var scopes = Object.keys(aligning);
        if (!scopes.length) return;
        var tokens = this._scrollToken || {};
        scopes.forEach(function (scope) {
          tokens[scope] = (tokens[scope] || 0) + 1;
        });
        this._scrollToken = tokens;
        this._aligning = {};
      },

      // Restore the stored position once the markers are loaded and the
      // messages rendered. Ignored if the user navigated away meanwhile.
      restoreViewPosition: function (channelId, threadTs, scrollerRef) {
        var self = this;
        var ready = this.readPositionsReady || Promise.resolve();
        return ready.then(function () {
          if (self.channelId !== channelId) return;
          if (threadTs && (!self.thread || self.thread.thread_ts !== threadTs)) return;
          var ts = self.readPosition(channelId, threadTs);
          if (ts) {
            self.scrollToMessage(ts, scrollerRef, { align: 'top', highlight: false });
          }
        });
      },

      onVisibilityChange: function () {
        if (document.visibilityState === 'hidden') this.flushReadPositions();
      },

      // -------------------------------------------------- channel view

      openChannel: function (channelId, opts) {
        opts = opts || {};
        var self = this;
        var switched = channelId !== this.channelId;
        // Persist the position in the conversation being left before its
        // messages are replaced.
        this.flushReadPositions();
        this.view = 'channel';
        this.channelId = channelId;
        this.channel = this.channelsById[channelId] ||
          { id: channelId, name: null, display_name: null, is_im: null, is_private: null };
        this.messages = [];
        this.hasMore = false;
        this.loadingMessages = true;
        // A refresh reload keeps the open thread panel; a real navigation
        // to another conversation closes it.
        if (!opts.keepThread) this.closeThread();
        return this._api('/api/channels/' + encodeURIComponent(channelId) + '/messages')
          .then(function (body) {
            if (body.channel && body.channel.name) {
              // Search hits can reach channels missing from the sidebar cache.
              self.channelsById[channelId] = body.channel;
            }
            self.channel = body.channel;
            self.rememberUsers(body.users);
            self.messages = body.messages;
            self.hasMore = body.has_more;
            self.loadingMessages = false;
            if (opts.highlight) {
              self.scrollToMessage(opts.highlight);
            } else if (opts.restore !== false) {
              // Returning to a conversation resumes where it was last read.
              self.restoreViewPosition(channelId, null, 'msgScroll');
            }
            if (switched) self.attemptChannelRefresh(channelId);
          })
          .catch(function (err) {
            self.loadingMessages = false;
            self.toast('Failed to load channel: ' + err.message, 'error');
          });
      },

      loadOlder: function () {
        if (!this.messages.length || this.loadingOlder) return;
        var self = this;
        var scroller = this.$refs.msgScroll;
        var beforeHeight = scroller ? scroller.scrollHeight : 0;
        this.loadingOlder = true;
        var oldest = this.messages[this.messages.length - 1].ts;
        this._api('/api/channels/' + encodeURIComponent(this.channelId) +
          '/messages?before=' + encodeURIComponent(oldest))
          .then(function (body) {
            self.rememberUsers(body.users);
            self.messages = self.messages.concat(body.messages);
            self.hasMore = body.has_more;
            self.loadingOlder = false;
            Vue.nextTick(function () {
              if (scroller) scroller.scrollTop = scroller.scrollHeight - beforeHeight;
            });
          })
          .catch(function (err) {
            self.loadingOlder = false;
            self.toast('Failed to load older messages: ' + err.message, 'error');
          });
      },

      // -------------------------------------------------- thread panel

      openThread: function (threadTs, highlightTs, opts) {
        opts = opts || {};
        var self = this;
        // Persist the position in the thread being left (if any) before
        // the panel is replaced.
        this.flushReadPositions();
        this.thread = {
          channel_id: this.channelId,
          thread_ts: threadTs,
          messages: [],
          loading: true,
        };
        return this._api('/api/channels/' + encodeURIComponent(this.channelId) +
          '/threads/' + encodeURIComponent(threadTs))
          .then(function (body) {
            if (!self.thread || self.thread.thread_ts !== threadTs) return;
            self.rememberUsers(body.users);
            self.thread.messages = body.messages;
            self.thread.loading = false;
            if (highlightTs) {
              Vue.nextTick(function () { self.scrollToMessage(highlightTs, 'threadScroll'); });
            } else if (opts.restore !== false) {
              // Reopening a thread resumes the reply the reader was on.
              self.restoreViewPosition(self.thread.channel_id, threadTs, 'threadScroll');
            }
          })
          .catch(function (err) {
            if (self.thread && self.thread.thread_ts === threadTs) {
              self.thread.loading = false;
            }
            self.toast('Failed to load thread: ' + err.message, 'error');
          });
      },

      closeThread: function () {
        this.flushReadPositions();
        this.thread = null;
      },

      openRootThread: function (msg) {
        if (msg.reply_count > 0) this.openThread(msg.ts);
      },

      // -------------------------------------------------- URL routing

      syncUrl: function () {
        if (this._skipUrlSync) return;
        var url = routeUrl({
          channelId: this.view === 'channel' ? this.channelId : null,
          threadTs: this.thread ? this.thread.thread_ts : null,
        });
        if (window.location.pathname + window.location.search !== url) {
          window.history.pushState(null, '', url);
        }
      },

      pauseUrlSync: function (mutate) {
        // Suppress pushState while applying a URL programmatically (boot,
        // back/forward): the address bar already holds the target URL.
        this._skipUrlSync = true;
        mutate();
        var self = this;
        Vue.nextTick(function () { self._skipUrlSync = false; });
      },

      applyRoute: function (route) {
        var self = this;
        // A URL that names a message or a thread wins over the stored
        // viewport, so the web-ui position must not pull either pane away
        // from the target the link points at.
        var targeted = !!(route.messageTs || route.threadTs);
        if (route.channelId === this.channelId && this.view === 'channel') {
          if (route.threadTs) {
            // Show the thread root in the channel, then the linked reply in
            // the panel.
            this.scrollToMessage(route.threadTs, 'msgScroll', { highlight: false });
            this.openThread(route.threadTs, route.messageTs, { restore: !targeted });
          } else {
            this.closeThread();
            if (route.messageTs) this.scrollToMessage(route.messageTs);
          }
          return;
        }
        this.openChannel(route.channelId, {
          highlight: route.threadTs ? null : route.messageTs,
          restore: !targeted,
        }).then(function () {
          if (route.threadTs) {
            self.scrollToMessage(route.threadTs, 'msgScroll', { highlight: false });
            self.openThread(route.threadTs, route.messageTs, { restore: !targeted });
          }
        });
      },

      applyLocation: function () {
        var self = this;
        var route = parseRoute(window.location.pathname, window.location.search);
        var url = routeUrl(route);
        if (window.location.pathname + window.location.search !== url) {
          window.history.replaceState(null, '', url);
        }
        if (!route || !route.channelId) {
          this.pauseUrlSync(this.goHome.bind(this));
          return;
        }
        this.pauseUrlSync(function () { self.applyRoute(route); });
      },

      onPopState: function () { this.applyLocation(); },

      goHome: function () {
        this.view = 'home';
        this.channelId = null;
        this.channel = null;
        this.messages = [];
        this.hasMore = false;
        this.loadingMessages = false;
        this.closeThread();
        this.closeProfile();
      },

      // -------------------------------------------------- refresh (live)

      refresh: function (label, path, after, opts) {
        opts = opts || {};
        if (this.refreshing) return;
        var self = this;
        this.refreshing = label;
        this.post(path).then(function (body) {
          self.refreshing = null;
          if (!opts.silent) {
            self.toast(label + ' complete' + self.refreshSummary(body), 'ok');
          }
          if (after) after(body);
        }).catch(function (err) {
          self.refreshing = null;
          if (!opts.silent) {
            self.toast(label + ' failed: ' + err.message, 'error');
          }
        });
      },

      refreshSummary: function (body) {
        var s = body && (body.channel || body.thread || body.users || body.channels);
        if (s && s.fetched_messages !== undefined) {
          return ' (' + s.fetched_messages + ' new, ' + s.total_messages + ' total)';
        }
        if (s && s.processed !== undefined) {
          return ' (' + s.added + ' new, ' + s.total + ' total)';
        }
        return '';
      },

      // Reload a conversation after a refresh without moving the reader.
      // The reload skips the stored position, so a permalink target or the
      // message the reader is on is never traded for the last viewed marker,
      // and the viewport is put back on the message that was at its top.
      reloadChannelAtViewport: function (channelId) {
        var self = this;
        if (this.channelId !== channelId) return Promise.resolve();
        var anchor = topVisibleAnchor(this.$refs.msgScroll);
        if (anchor) this.rememberPosition(channelId, null, anchor.ts);
        return this.openChannel(channelId, { restore: false, keepThread: true }).then(function () {
          if (!anchor || self.channelId !== channelId) return;
          self.scrollToMessage(anchor.ts, 'msgScroll', { offset: anchor.offset, highlight: false });
        });
      },

      reloadThreadAtViewport: function () {
        var self = this;
        var thread = this.thread;
        if (!thread) return Promise.resolve();
        var anchor = topVisibleAnchor(this.$refs.threadScroll);
        if (anchor) this.rememberPosition(thread.channel_id, thread.thread_ts, anchor.ts);
        return this.openThread(thread.thread_ts, null, { restore: false }).then(function () {
          if (!anchor || !self.thread || self.thread.thread_ts !== thread.thread_ts) return;
          self.scrollToMessage(anchor.ts, 'threadScroll', { offset: anchor.offset, highlight: false });
        });
      },

      // Switching conversations silently refreshes the target in the
      // background: cached messages render immediately, fresh ones replace
      // them when the fetch lands. Best effort, so failures (no
      // credentials, unknown channel) stay quiet. The fetch re-reads the
      // last few days of history (no thread crawl), which picks up new
      // messages plus edits and deletions inside that window in one or two
      // quick Slack calls; the "Refresh from Slack" button remains the full
      // history + threads refresh.
      attemptChannelRefresh: function (channelId) {
        var self = this;
        var windowStart = Date.now() / 1000 - AUTO_REFRESH_WINDOW_DAYS * 86400;
        var query = '?full_threads=false&oldest=' +
          encodeURIComponent(windowStart.toFixed(6));
        this.refresh('Channel refresh',
          '/api/channels/' + encodeURIComponent(channelId) + '/refresh' + query,
          function () {
            // Only reload if the user is still on that conversation.
            if (self.channelId === channelId) self.reloadChannelAtViewport(channelId);
          },
          { silent: true });
      },

      refreshChannel: function () {
        var self = this;
        var id = this.channelId;
        this.refresh('Channel refresh',
          '/api/channels/' + encodeURIComponent(id) + '/refresh',
          function () { self.reloadChannelAtViewport(id); });
      },

      refreshThread: function () {
        var self = this;
        if (!this.thread) return;
        var ts = this.thread.thread_ts;
        // full=true forces a complete fetch so deletions inside the thread
        // are reconciled; the incremental window cannot detect them.
        this.refresh('Thread refresh',
          '/api/channels/' + encodeURIComponent(this.channelId) +
          '/threads/' + encodeURIComponent(ts) + '/refresh?full=true',
          function () { self.reloadThreadAtViewport(); });
      },

      refreshUsers: function () {
        var self = this;
        this.refresh('User refresh', '/api/users/refresh', function () {
          self.loadDirectory();
          self._api('/api/summary').then(function (body) { self.summary = body; });
        });
      },

      refreshChannels: function () {
        var self = this;
        this.refresh('Channel refresh', '/api/channels/refresh', function () {
          self.loadDirectory();
          self._api('/api/summary').then(function (body) { self.summary = body; });
        });
      },

      // -------------------------------------------------- palette

      openPalette: function () {
        this.closeProfile();
        this.paletteOpen = true;
        this.paletteQuery = '';
        this.paletteMsgsLoading = false;
        this.paletteItems = this.localMatches('');
        this.paletteActive = 0;
        var self = this;
        Vue.nextTick(function () {
          if (self.$refs.paletteInput) self.$refs.paletteInput.focus();
        });
      },

      closePalette: function () {
        this.paletteOpen = false;
        this.paletteSearchSeq++;
        if (this.paletteTimer) clearTimeout(this.paletteTimer);
      },

      localMatches: function (q) {
        var needle = q.trim().toLowerCase();
        var label = function (c) { return c.display_name || c.name || c.id; };
        var channels = this.channels.filter(function (c) {
          if (!needle) return true;
          return label(c).toLowerCase().indexOf(needle) !== -1 ||
            c.id.toLowerCase().indexOf(needle) !== -1;
        }).sort(function (a, b) {
          var aStarts = label(a).toLowerCase().startsWith(needle) ? 1 : 0;
          var bStarts = label(b).toLowerCase().startsWith(needle) ? 1 : 0;
          return (bStarts - aStarts) || (b.message_count - a.message_count);
        }).slice(0, 8).map(function (c) {
          return {
            key: 'c-' + c.id,
            type: 'channel',
            id: c.id,
            name: label(c),
            is_im: c.is_im,
            is_private: c.is_private,
            message_count: c.message_count,
          };
        });

        var people = needle ? this.users.filter(function (u) {
          return u.display_name.toLowerCase().indexOf(needle) !== -1 ||
            (u.name || '').toLowerCase().indexOf(needle) !== -1;
        }).slice(0, 5).map(function (u) {
          return { key: 'u-' + u.id, type: 'person', user: u };
        }) : [];

        return channels.concat(people);
      },

      onPaletteInput: function () {
        var self = this;
        var q = this.paletteQuery;
        var seq = ++this.paletteSearchSeq;
        if (this.paletteTimer) clearTimeout(this.paletteTimer);
        this.paletteItems = [];
        this.paletteActive = 0;
        this.paletteMsgsLoading = false;
        this.paletteTimer = setTimeout(function () { self.searchPalette(q, seq); }, 180);
      },

      searchPalette: function (q, seq) {
        var trimmed = q.trim();
        if (!trimmed || q !== this.paletteQuery || !this.paletteOpen) return;
        var self = this;
        var param = '?q=' + encodeURIComponent(trimmed);
        this.paletteMsgsLoading = trimmed.length >= 2;
        Promise.all([
          this._api('/api/channels' + param + '&limit=8'),
          this._api('/api/users' + param + '&limit=5'),
        ]).then(function (results) {
          if (seq !== self.paletteSearchSeq || !self.paletteOpen) return;
          var channels = results[0].channels.map(function (c) {
            return { key: 'c-' + c.id, type: 'channel', id: c.id,
              name: c.display_name || c.name || c.id, is_im: c.is_im,
              is_private: c.is_private, message_count: c.message_count };
          });
          var people = results[1].users.map(function (u) {
            return { key: 'u-' + u.id, type: 'person', user: u };
          });
          // Keep any message hits that arrived before the directory lookup.
          self.paletteItems = channels.concat(people, self.paletteItems.filter(function (item) {
            return item.type === 'message';
          }));
          if (self.paletteActive >= self.paletteItems.length) self.paletteActive = 0;
        }).catch(function (err) {
          if (seq !== self.paletteSearchSeq) return;
          self.toast('Search failed: ' + err.message, 'error');
        });
        if (trimmed.length < 2) return;
        this._api('/api/search' + param + '&limit=12').then(function (body) {
          if (seq !== self.paletteSearchSeq || !self.paletteOpen) return;
          self.paletteMsgsLoading = false;
          self.paletteItems = self.paletteItems.filter(function (item) {
            return item.type !== 'message';
          }).concat(body.hits.map(function (h) {
            return { key: 'm-' + h.channel + '-' + h.ts, type: 'message', hit: h };
          }));
          if (self.paletteActive >= self.paletteItems.length) self.paletteActive = 0;
        }).catch(function (err) {
          if (seq !== self.paletteSearchSeq) return;
          self.paletteMsgsLoading = false;
          self.toast('Message search failed: ' + err.message, 'error');
        });
      },

      onPaletteKey: function (e) {
        if (e.key === 'ArrowDown') {
          e.preventDefault();
          this.paletteMove(1);
        } else if (e.key === 'ArrowUp') {
          e.preventDefault();
          this.paletteMove(-1);
        } else if (e.key === 'Enter') {
          e.preventDefault();
          this.paletteChoose();
        } else if (e.key === 'Escape') {
          this.closePalette();
        }
      },

      paletteMove: function (delta) {
        var n = this.paletteItems.length;
        if (!n) return;
        this.paletteActive = (this.paletteActive + delta + n) % n;
        var el = this.$refs.paletteResults;
        var node = el && el.querySelector('.palette-item.active');
        if (node) node.scrollIntoView({ block: 'nearest' });
      },

      paletteChoose: function () {
        var item = this.paletteItems[this.paletteActive];
        if (item) this.chooseItem(item);
      },

      chooseItem: function (item) {
        this.closePalette();
        if (item.type === 'channel') {
          this.openChannel(item.id);
        } else if (item.type === 'person') {
          this.showProfile(item.user);
        } else if (item.type === 'message') {
          this.jumpToMessage(item.hit);
        }
      },

      jumpToMessage: function (hit) {
        this.openMessageLink({
          channelId: hit.channel,
          messageTs: hit.ts,
          threadTs: hit.ts === hit.thread_ts ? null : hit.thread_ts,
        });
      },

      // Follow a message permalink (timestamp link or palette hit): push the
      // URL, then let applyRoute open the channel/thread and highlight.
      openMessageLink: function (target) {
        var url = routeUrl(target);
        if (window.location.pathname + window.location.search !== url) {
          window.history.pushState(null, '', url);
        }
        this.applyRoute(target);
      },

      scrollToMessage: function (ts, scrollerRef, opts) {
        opts = opts || {};
        var self = this;
        var scope = scrollerRef || 'msgScroll';
        // Each call cancels the alignment loop of a previous one for the
        // same scroller; the two panes align independently.
        var tokens = this._scrollToken || {};
        var token = (tokens[scope] = (tokens[scope] || 0) + 1);
        this._scrollToken = tokens;
        if (opts.highlight !== false) this.highlightTs = ts;
        Vue.nextTick(function () {
          var scroller = self.$refs[scope];
          var el = findMessageRow(scroller, ts);
          if (!el || !scroller) return;
          // Reapply the alignment for a short while: the browser injects
          // Tailwind styles and fonts after the first render, which shifts
          // rows and would otherwise leave the viewport a few messages off.
          // A real scroll by the reader cancels the loop (see on*Scroll).
          var delays = [50, 100, 200, 400, 800];
          var attempts = 0;
          var align = function () {
            if (tokens[scope] !== token || !document.contains(el)) return;
            // offsetTop is unreliable here (positioned ancestors); use rects.
            var top = el.getBoundingClientRect().top -
              scroller.getBoundingClientRect().top + scroller.scrollTop;
            if (opts.offset != null) {
              // Put an anchor row back where it was in the viewport; a
              // negative offset means it started above the top edge.
              scroller.scrollTop = top - opts.offset;
            } else if (opts.align === 'top') {
              // A restored position puts the message at the top so the
              // viewport matches when it was left.
              scroller.scrollTop = top;
            } else {
              // Permalinks center the message for context.
              scroller.scrollTop = top - scroller.clientHeight / 3;
            }
            var aligning = Object.assign({}, self._aligning);
            aligning[scope] = { top: scroller.scrollTop };
            self._aligning = aligning;
            if (attempts < delays.length) {
              setTimeout(align, delays[attempts]);
              attempts += 1;
            } else {
              setTimeout(function () {
                if (tokens[scope] !== token) return;
                var done = Object.assign({}, self._aligning);
                delete done[scope];
                self._aligning = done;
              }, 200);
            }
          };
          align();
        });
        if (opts.highlight !== false) {
          setTimeout(function () { self.highlightTs = null; }, 2500);
        }
      },

      // -------------------------------------------------- profile

      showProfile: function (user) { this.profile = user; },

      closeProfile: function () { this.profile = null; },

      // -------------------------------------------------- theme

      applyTheme: function () {
        // Resolve the active data-theme; "System" follows the OS setting.
        var theme = this.theme;
        if (theme === 'system') {
          theme = window.matchMedia('(prefers-color-scheme: dark)').matches
            ? 'dark' : 'light';
        }
        document.documentElement.setAttribute('data-theme', theme);
      },

      setTheme: function (theme) {
        this.theme = theme;
        this.applyTheme();
        try {
          localStorage.setItem('slackx-theme', theme);
        } catch (e) { /* private mode etc.; theme still applies for the session */ }
      },

      chooseTheme: function (theme, evt) {
        this.setTheme(theme);
        // Close the dropdown: it stays open while any descendant holds focus
        // (the menu ul is tabindex=0, so it can retain focus after a click).
        var dropdown = evt.currentTarget.closest('.dropdown');
        if (dropdown && dropdown.contains(document.activeElement)) {
          document.activeElement.blur();
        }
      },

      // -------------------------------------------------- global

      globalKey: function (e) {
        if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'p') {
          e.preventDefault();
          if (this.paletteOpen) this.closePalette();
          else this.openPalette();
        } else if (e.key === 'Escape' && this.profile) {
          this.closeProfile();
        }
      },

      onMainClick: function (e) {
        var t = e.target.closest('[data-channel]');
        if (t) this.openChannel(t.getAttribute('data-channel'));
      },
    },

    mounted: function () {
      var self = this;
      document.addEventListener('keydown', this.globalKey);
      window.addEventListener('popstate', this.onPopState);
      // Save the last position when the page is hidden or closed; the
      // debounced write may not have fired yet.
      window.addEventListener('pagehide', this.flushReadPositions);
      document.addEventListener('visibilitychange', this.onVisibilityChange);
      // A real scroll by the reader takes over from an in-flight alignment.
      this._onUserInput = function () { self.cancelAlignment(); };
      USER_INPUT_EVENTS.forEach(function (type) {
        document.addEventListener(type, self._onUserInput, { passive: true, capture: true });
      });
      // Follow OS light/dark changes while "System" is selected.
      if (window.matchMedia) {
        var mq = window.matchMedia('(prefers-color-scheme: dark)');
        this._onSystemThemeChange = function () {
          if (self.theme === 'system') self.applyTheme();
        };
        if (mq.addEventListener) {
          mq.addEventListener('change', this._onSystemThemeChange);
        } else if (mq.addListener) {
          mq.addListener(this._onSystemThemeChange); // older browsers
        }
      }
      var stored = null;
      try {
        stored = localStorage.getItem('slackx-theme');
      } catch (e) { /* ignore */ }
      this.setTheme(THEMES.indexOf(stored) !== -1 ? stored : 'system');
      this.boot();
    },

    beforeUnmount: function () {
      document.removeEventListener('keydown', this.globalKey);
      window.removeEventListener('popstate', this.onPopState);
      window.removeEventListener('pagehide', this.flushReadPositions);
      document.removeEventListener('visibilitychange', this.onVisibilityChange);
      var self = this;
      USER_INPUT_EVENTS.forEach(function (type) {
        document.removeEventListener(type, self._onUserInput, true);
      });
      if (window.matchMedia) {
        var mq = window.matchMedia('(prefers-color-scheme: dark)');
        if (mq.removeEventListener) {
          mq.removeEventListener('change', this._onSystemThemeChange);
        } else if (mq.removeListener) {
          mq.removeListener(this._onSystemThemeChange);
        }
      }
    },
  });

  // One avatar: the user's photo when available, else the colored
  // initials placeholder (also used as the on-image-error fallback).
  app.component('user-avatar', {
    props: {
      src: { type: String, default: '' },
      name: { type: String, required: true },
      id: { type: String, default: '' },
      boxClass: { type: String, default: 'w-9 rounded-md' },
      textClass: { type: String, default: 'text-[11px] font-bold uppercase' },
    },
    data: function () { return { failed: false }; },
    computed: {
      showImage: function () { return this.src && !this.failed; },
      style: function () {
        return this.showImage ? undefined : { background: colorFor(this.id || this.name) };
      },
    },
    methods: { initials: initials },
    template: [
      // daisyUI 5 centers initials via the single .avatar-placeholder class.
      '<div class="avatar" :class="{ \'avatar-placeholder\': !showImage }">',
      '  <div class="overflow-hidden" :class="boxClass" :style="style">',
      '    <img v-if="showImage" :src="src" :alt="name" loading="lazy"',
      '         referrerpolicy="no-referrer" @error="failed = true">',
      '    <span v-else :class="textClass">{{ initials(name) }}</span>',
      '  </div>',
      '</div>',
    ].join(''),
  });

  // One message (avatar, author, time, mrkdwn text, optional thread bar).
  // ``ctx`` carries the user/channel maps needed for mention resolution plus
  // channelId/threadTs for building the message's permalink URL.
  app.component('message-row', {
    props: {
      msg: { type: Object, required: true },
      ctx: { type: Object, required: true },
      highlight: { type: Boolean, default: false },
      showThreadBar: { type: Boolean, default: false },
    },
    emits: ['open-thread', 'navigate'],
    computed: {
      html: function () { return renderMessageHtml(this.msg, this.ctx); },
      author: function () { return this.msg.user_name || this.msg.user || 'unknown'; },
      time: function () { return fmtTime(tsToDate(this.msg.ts)); },
      avatar: function () {
        return (this.ctx.userAvatars && this.ctx.userAvatars[this.msg.user]) || '';
      },
      // Archive annotations, Slack-style: content that changed or
      // disappeared on Slack stays visible here with a marker.
      edited: function () { return !!(this.msg.payload && this.msg.payload.edited); },
      deleted: function () { return !!(this.msg.payload && this.msg.payload.deleted); },
      // Route target for this message. Inside an open thread each message
      // links to itself (path ts) with the thread root in thread_ts, so
      // opening the URL on page load restores the thread panel and
      // highlights the linked message; elsewhere a message links to itself
      // only.
      linkTarget: function () {
        return {
          channelId: this.ctx.channelId || '',
          messageTs: this.msg.ts,
          threadTs: this.ctx.threadTs || null,
        };
      },
      permalink: function () {
        return this.linkTarget.channelId ? routeUrl(this.linkTarget) : '';
      },
    },
    methods: {
      rel: fmtRelative,
    },
    template: [
      '<div class="msg flex gap-2.5 px-5 py-1" :data-ts="msg.ts" :id="\'m-\' + msg.ts.replace(\'.\', \'-\')" :class="{highlight: highlight}">',
      '  <user-avatar :src="avatar" :name="author" :id="msg.user"></user-avatar>',
      '  <div class="min-w-0 flex-1">',
      '    <div class="flex items-baseline gap-2">',
      '      <span class="font-black text-base-content">{{ author }}</span>',
      '      <span class="badge badge-ghost badge-xs" v-if="msg.payload && msg.payload.bot_id">APP</span>',
      '      <a v-if="permalink" class="text-xs opacity-50 hover:underline" :href="permalink"',
      '         :title="\'Permalink to this message\'" @click.stop.prevent="$emit(\'navigate\', linkTarget)">{{ time }}</a>',
      '      <span v-else class="text-xs opacity-50">{{ time }}</span>',
      '      <span v-if="edited" class="text-xs italic opacity-60" title="Message was edited on Slack">(edited)</span>',
      '      <span v-if="deleted" class="text-xs italic font-semibold text-error opacity-80" title="Message was deleted on Slack; content preserved by the cache">(deleted)</span>',
      '    </div>',
      '    <div class="text whitespace-pre-wrap break-words" :class="{ \'opacity-60\': deleted }" v-html="html"></div>',
      '    <button v-if="showThreadBar && msg.reply_count > 0" class="thread-bar btn btn-ghost btn-xs -ml-1 mt-0.5 px-1 text-primary"',
      '            @click.stop="$emit(\'open-thread\', msg)">',
      '      &#128172; {{ msg.reply_count === 1 ? \'1 reply\' : msg.reply_count + \' replies\' }}',
      '      <template v-if="msg.latest_reply_ts">&middot; last reply {{ rel(msg.latest_reply_ts) }}</template>',
      '    </button>',
      '  </div>',
      '</div>',
    ].join(''),
  });

  app.mount('#app');
})();
