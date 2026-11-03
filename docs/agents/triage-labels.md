# Triage Labels

The skills speak in terms of six canonical triage roles. This file maps those roles to the actual label strings used in this repo's issue tracker.

| Label in mattpocock/skills | Label in our tracker | Meaning                                                                                                |
| -------------------------- | -------------------- | ------------------------------------------------------------------------------------------------------ |
| `needs-triage`             | `needs-triage`       | Maintainer needs to evaluate this issue                                                                |
| `needs-info`               | `needs-info`         | Needs grilling (our tickets) or more information from the reporter (outside issues) before it is built |
| `ready-for-agent`          | `ready-for-agent`    | Fully specified, ready for an AFK agent                                                                |
| `ready-for-human`          | `ready-for-human`    | Specified, but a human builds it (a taste call, credentials, or work the owner writes)                 |
| `backlog`                  | `backlog`            | Real work, parked until scheduled                                                                      |
| `wontfix`                  | `wontfix`            | Will not be actioned                                                                                   |

Not routing roles, each with its string equal to its name: `bug` and `enhancement` (the category roles `/triage` adds), and `spec` (a parent reference `/to-spec` and `/to-tickets` add beside `ready-for-agent`, which a burn hands to `/implement-spec`).

When a skill mentions a role (e.g. "apply the AFK-ready triage label"), use the corresponding label string from this table.
