# Arch Morning View

MVP specification for one advisor’s morning review of private-market documents.

Arch is the system of record. Fund managers send documents, mostly capital call notices and investor letters. Those documents have to land on the right fund, and the advisor has to see what needs action today without mixing up clients.

## Who

- One advisor. Their account is created the first time the app runs, with a name and password.
- One login per client, created by the advisor, also a name and password.
- The advisor picks a client and manages that client’s funds and documents.
- A client sees only their own funds and documents. Another client’s funds and documents never appear on their screen.

## How

Both people use the app in a browser on one computer and sign in with a name and password.

The advisor opens one client at a time. That screen shows:

1. Unpaid capital calls first, soonest due date first, with the fund name and the amount.
2. That client’s funds underneath.
3. Each fund’s documents under the fund.

The advisor can add, change, and delete clients, funds, and documents.

- Deleting a client removes that client’s login, funds, and documents.
- Deleting a fund removes its documents.

A document is filed on a fund. It is either:

- A capital call, with an amount due and a due date.
- An investor letter, with a short summary of what changed.

Marking a call paid takes it off the morning list. It stays on the fund. Changing it back to unpaid puts it on the morning list again. Only the advisor can change this status.

The client’s screen lists every document, grouped by fund. On a capital call they see the real paid status and their own checkmark. That checkmark is saved for them. It does not change the real status, and the advisor never sees it.

## What

- React in the browser.
- FastAPI on the server.
- SQLite for storage.

Data is still there after a restart. Passwords are stored hashed. The server is the source of truth for funds, documents, paid status, and each client’s checkmark.

## Later

An archive of deleted clients, funds, or documents. Not part of this MVP.
