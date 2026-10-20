---
title: "JSON-RPC API"
status: done
---

# Requirements: JSON-RPC API

## Overview

slackx is normally driven by one CLI process per operation.
Clients that need many reads, or that run alongside a browser UI, pay process startup, argument parsing, and workspace resolution every time.
This feature exposes the CLI's operations as a JSON-RPC 2.0 API on the FastAPI server, so a client can call one long-running server instance instead.

The server is the app already built by `slackx.server.app.create_app`, which `slackx serve` runs.
`slackx rpc serve` runs the same app when only the API is needed.
`slackx rpc call` and `slackx rpc methods` are thin clients, `slackx rpc exec` and the global `--remote` mode reach every CLI command through `cli.run`, and `slackx.rpc.client.RpcClient` is the Python client.
The interface matches the one implemented by the sibling `ghx` project, using `--host` and `--port` for the listen address.

## Stakeholders

| Stakeholder | Interest |
|---|---|
| CLI user | Wants one warm server instead of a process per operation |
| Client program | Needs a typed, JSON-native request/response surface |
| Web UI | Shares the same server and database without a second process |
| Maintainer | Wants the RPC surface to reuse the CLI's logic instead of duplicating it |

## Functional Requirements

| ID | Priority | Requirement |
|---|---|---|
| FR-1 | Must | The server shall accept JSON-RPC 2.0 requests at `POST /rpc` on the app built by `create_app` |
| FR-2 | Must | The server shall accept one request object, a batch array, and notifications (a request without `id`) |
| FR-3 | Must | The server shall expose `rpc.discover`, returning the server name, version, and each method's name, description, and parameter names, with `system.methods` kept as an alias |
| FR-3a | Must | The server shall expose `server.info`, returning the server name, version, workspace, database path, execution setting, method count, and start time |
| FR-4 | Must | The server shall expose cache operations as `cache.status` and `cache.clear` |
| FR-5 | Must | The server shall expose `users.list` and `users.get` |
| FR-6 | Must | The server shall expose `channels.list` and `channels.get` |
| FR-7 | Must | The server shall expose `conversations.fetch`, `conversations.get`, and `conversations.search` |
| FR-8 | Must | The server shall expose `read.mark`, `read.show`, and `read.clear` |
| FR-9 | Must | Each method shall reject unknown parameters and invalid parameter types with `-32602` |
| FR-10 | Must | The server shall map parse, request, method, and application failures to distinct JSON-RPC error codes |
| FR-11 | Must | The CLI shall provide `rpc serve`, `rpc call`, and `rpc methods` |
| FR-12 | Must | `rpc call` shall print the JSON result to stdout and report JSON-RPC errors on stderr with a non-zero exit |
| FR-13 | Must | Results shall match the CLI's `--json` payloads where the corresponding command has one |
| FR-14 | Must | `conversations.get` shall advance the named reader's pointer, matching the CLI, and skip it when `reader` is null |
| FR-15 | Should | The server's database path and Slack API base URL shall be fixed at startup and not settable per request |
| FR-16 | Should | A Python client shall be available as `slackx.rpc.client.RpcClient` |
| FR-17 | Must | The server shall expose `cli.run`, which executes a CLI command in a child process and returns stdout, stderr, and the exit code |
| FR-18 | Must | `cli.run` shall be removable from the catalog with `--no-allow-exec`, and calls to it shall then return `-32601` |
| FR-19 | Must | The CLI shall provide `rpc exec` and a global `--remote [URL]` mode that forward any command to `cli.run`, mirror output, and mirror the remote exit code |
| FR-20 | Must | The server shall accept an optional bearer token from `--token` (`--rpc-token` on `serve`) or `SLACKX_RPC_TOKEN`, and shall refuse a non-loopback bind without one |
| FR-21 | Must | `rpc serve` and `serve` shall use `--host` and `--port` for the listen address |

## Non-Functional Requirements

| ID | Priority | Category | Requirement |
|---|---|---|---|
| NFR-1 | Must | Security | The RPC endpoint shall not accept a database path, workspace, or Slack base URL from the client |
| NFR-2 | Must | Reliability | The transport shall not leak a traceback to the caller; unexpected failures become a `-32000` error |
| NFR-3 | Must | Compatibility | Adding the RPC endpoint shall not change the existing HTTP API, web UI routes, or CLI commands |
| NFR-4 | Must | Maintainability | RPC results and CLI JSON results shall come from the same payload-building functions |
| NFR-5 | Should | Performance | Read methods shall reuse the server's cache reads without a network call when the data is cached |
| NFR-6 | Should | Testability | The RPC surface shall be exercisable through FastAPI's `TestClient` without a network listener |

## Constraints

- The JSON-RPC endpoint is served by the same FastAPI app as the web UI.
- Method parameters are a JSON object; by-position parameters are not supported.
- `conversations.poll`, `serve`, and the fake Slack server are long-running processes and are not exposed as methods.
- Credentials are resolved from the server process's environment or config file, as for the CLI.

## Acceptance Criteria

- [ ] **FR-1**

    ```gherkin
    @FR-1
    Scenario: The serve app exposes the RPC endpoint
      Given a running slackx server
      When a client posts a JSON-RPC request to /rpc
      Then the server answers with a JSON-RPC response
    ```

- [ ] **FR-2**

    ```gherkin
    @FR-2
    Scenario: Batch and notification handling
      Given a running slackx server
      When a client posts an array with one request and one notification
      Then the response array contains exactly the request's response
      And a notification alone returns HTTP 204 with no body
    ```

- [ ] **FR-3**

    ```gherkin
    @FR-3
    Scenario: Method catalog
      Given a running slackx server
      When a client calls system.methods
      Then the result lists every exposed method with its parameters
    ```

- [ ] **FR-4**

    ```gherkin
    @FR-4
    Scenario: Cache status and clear
      Given a cache with users and channels
      When a client calls cache.status
      Then the result reports the counts
      When a client calls cache.clear with target users
      Then the user rows are removed and the channels remain
    ```

- [ ] **FR-5**

    ```gherkin
    @FR-5
    Scenario: User methods
      Given a cache with a user
      When a client calls users.list with fetch false
      Then the result contains the cached user
      When a client calls users.get for a missing user with fetch false
      Then the server returns a -32000 error
    ```

- [ ] **FR-6**

    ```gherkin
    @FR-6
    Scenario: Channel methods
      Given a cache with a channel
      When a client calls channels.list with fetch false
      Then the result contains the cached channel
    ```

- [ ] **FR-7**

    ```gherkin
    @FR-7
    Scenario: Conversation methods
      Given a cached channel and thread
      When a client calls conversations.get with fetch false
      Then the result contains the cached messages with resolved author names
    ```

- [ ] **FR-8**

    ```gherkin
    @FR-8
    Scenario: Read marker methods
      Given a cached channel
      When a client calls read.mark for a reader
      Then read.show returns that reader's pointer
      When the client calls read.clear for that reader
      Then read.show returns no pointers
    ```

- [ ] **FR-9**

    ```gherkin
    @FR-9
    Scenario: Invalid parameters
      When a client sends an unknown parameter or a string where an integer is required
      Then the server returns error code -32602
    ```

- [ ] **FR-10**

    ```gherkin
    @FR-10
    Scenario: Error codes
      When the request body is not JSON
      Then the server returns -32700
      When the request is not a valid JSON-RPC object
      Then the server returns -32600
      When the method does not exist
      Then the server returns -32601
      When a method fails at runtime
      Then the server returns -32000
    ```

- [ ] **FR-11**

    ```gherkin
    @FR-11
    Scenario: RPC CLI commands
      When the user runs `slackx rpc methods` against a server
      Then the command lists the methods
      When the user runs `slackx rpc call users.list --params '{"fetch": false}'`
      Then the command prints the JSON result
    ```

- [ ] **FR-12**

    ```gherkin
    @FR-12
    Scenario: RPC call failure
      When a method returns a JSON-RPC error
      Then `slackx rpc call` prints the error on stderr and exits non-zero
    ```

- [ ] **FR-13**

    ```gherkin
    @FR-13
    Scenario: Result parity with CLI JSON
      Given a cached thread
      When a client calls conversations.get and the CLI runs `conversations get --json`
      Then both produce the same payload keys and message fields
    ```

- [ ] **FR-14**

    ```gherkin
    @FR-14
    Scenario: Read pointer parity
      When conversations.get runs with reader web
      Then the web reader's pointer advances to the newest cached message
      When it runs with reader null
      Then no pointer is written
    ```

- [ ] **FR-15**

    ```gherkin
    @FR-15
    Scenario: Server-bound state
      When a client sends db_path or api_base_url in params
      Then the method rejects the unknown parameter
    ```

- [ ] **FR-16**

    ```gherkin
    @FR-16
    Scenario: Python client
      When a program calls `await RpcClient(url).call("users.list", {"fetch": False})`
      Then it receives the result
      And a JSON-RPC error raises RpcError
    ```

- [ ] **FR-17**

    ```gherkin
    @FR-17
    Scenario: Run a CLI command over RPC
      Given a running slackx server
      When a client calls cli.run with args ["cache", "status", "--json"]
      Then the result contains stdout, stderr, and exitCode 0
      And the stdout is the CLI's JSON status payload
    ```

- [ ] **FR-18**

    ```gherkin
    @FR-18
    Scenario: Command execution is disabled
      Given a server started with --no-allow-exec
      When a client calls rpc.discover
      Then cli.run is absent from the catalog
      When a client calls cli.run
      Then the server returns -32601
    ```

- [ ] **FR-19**

    ```gherkin
    @FR-19
    Scenario: Forward a command from the CLI
      Given a running slackx server
      When the user runs `slackx rpc exec -- cache status --json`
      Then the server runs the command and the output is printed
      And a failing remote command makes the client exit with its code
    ```

- [ ] **FR-20**

    ```gherkin
    @FR-20
    Scenario: Token authentication
      Given a server started with --token secret
      When a request arrives without the token
      Then it receives HTTP 401
      When the request sends Authorization: Bearer secret
      Then it is handled normally
    ```

- [ ] **FR-21**

    ```gherkin
    @FR-21
    Scenario: Listen address flags
      When the user runs `slackx rpc serve --host 127.0.0.1 --port 9000`
      Then the server listens on 127.0.0.1:9000
    ```

- [ ] **NFR-1**

    ```gherkin
    @NFR-1
    Scenario: No client-selected database
      When a client calls any method with a database or workspace parameter
      Then the call fails with -32602
    ```

- [ ] **NFR-2**

    ```gherkin
    @NFR-2
    Scenario: No traceback in the response
      When a handler raises an unexpected exception
      Then the response contains a -32000 error and no traceback
    ```

- [ ] **NFR-3**

    ```gherkin
    @NFR-3
    Scenario: Existing surfaces keep working
      When the full test suite runs
      Then the CLI, web API, and storage tests still pass
    ```

- [ ] **NFR-4**

    ```gherkin
    @NFR-4
    Scenario: Shared payload builders
      When the CLI renders JSON
      Then it calls the same payload builder the RPC method uses
    ```

- [ ] **NFR-5**

    ```gherkin
    @NFR-5
    Scenario: Cached reads stay offline
      When a client calls a read method with fetch false
      Then no Slack client is built
    ```

- [ ] **NFR-6**

    ```gherkin
    @NFR-6
    Scenario: Tests run in process
      When the RPC tests run
      Then they drive the app through TestClient without a listening socket
    ```
