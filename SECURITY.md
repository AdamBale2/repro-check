# Security policy

repro-check runs untrusted code from issues, so we take isolation bugs seriously.

## Reporting a vulnerability

Please **do not** open a public issue. Use GitHub's private reporting instead:
the "Security" tab of this repository, then "Report a vulnerability".

Useful details: what you ran, what you could reach from inside the container
(network, files, environment, the Docker socket, the runner's token), and the
Docker version if you know it.

We aim to acknowledge reports within 7 days.

## In scope

- escaping the container or reaching the network from it;
- reading secrets or the workflow token from the example;
- making repro-check run code outside the container (for example through the issue text);
- making the posted comment misleading in a way that harms maintainers.

## Supported versions

Only the latest release receives fixes while the project is pre-1.0.
