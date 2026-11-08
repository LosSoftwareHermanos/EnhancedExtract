# Security policy

## Supported versions

Only the [latest release](https://github.com/LosSoftwareHermanos/EnhancedExtract/releases/latest) gets fixes. Please check that a problem still happens there before reporting it.

## Reporting a vulnerability

**Do not open a public issue for security problems.**

Report privately through GitHub: [open a private vulnerability report](https://github.com/LosSoftwareHermanos/EnhancedExtract/security/advisories/new) (Security tab, then **Report a vulnerability**). Only the maintainers can see it.

Please include:

- the EnhancedExtract version and Windows version
- what an attacker could do, and the steps or a sample file that shows it
- whether it needs a crafted archive or ISO, a particular folder, or administrator rights

You should get a first reply within 7 days. Once a fix is released, the advisory is published with credit to you unless you prefer not to be named.

## What is in scope

EnhancedExtract handles untrusted archives and ISOs and can delete files, so these matter most:

- files written outside the chosen destination (path traversal, links, device names)
- source files deleted when they should not be, or deleted before their contents are safely extracted
- code running with more rights than expected, for example through the Explorer menu, the elevated shortcuts or the ISO virtual drive
- the installer or uninstaller replacing, running or deleting files it should not

Bugs in bundled third-party tools (UnRAR, 7-Zip, WinFsp) should also be reported to their authors. Tell us too, so we can ship the fixed version.
