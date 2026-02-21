# CHANGELOG

<!-- version list -->

## v1.2.6 (2026-02-20)

### Bug Fixes

- **init**: Removing the max printer limit ([#22](https://github.com/PrintQue-ca/PrintQue/pull/22),
  [`bd56346`](https://github.com/PrintQue-ca/PrintQue/commit/bd56346c5d48458f6d9850c214dc8ef730984f79))

- **version-bump.yml**: Updating to use PrintQue GitHub app
  ([#23](https://github.com/PrintQue-ca/PrintQue/pull/23),
  [`8b8992f`](https://github.com/PrintQue-ca/PrintQue/commit/8b8992fdb248114c9d18db75328067d5e77075e9))


## v1.2.5 (2026-02-19)

### Bug Fixes

- **license.tsx**: Updating the discord invite link to not expire
  ([#21](https://github.com/PrintQue-ca/PrintQue/pull/21),
  [`864a35b`](https://github.com/PrintQue-ca/PrintQue/commit/864a35b07f52be530f4592f5d198ad3bb5c1ae46))

### Continuous Integration

- **release.yml**: Release submit to a forum channel
  ([#20](https://github.com/PrintQue-ca/PrintQue/pull/20),
  [`4a5f891`](https://github.com/PrintQue-ca/PrintQue/commit/4a5f891251a7e3feadb04dc5da70e412947774d5))


## v1.2.4 (2026-02-08)

### Bug Fixes

- Localhost origin source looser and adding discord release workflow
  ([#19](https://github.com/PrintQue-ca/PrintQue/pull/19),
  [`37fafc8`](https://github.com/PrintQue-ca/PrintQue/commit/37fafc8127943247b5a2e8fc9917612c70d87c4b))

### Chores

- Remove CodeQL workflow configuration ([#17](https://github.com/PrintQue-ca/PrintQue/pull/17),
  [`4434dea`](https://github.com/PrintQue-ca/PrintQue/commit/4434deae9fd003425c77dd64c13e3763347df303))

- Update package dependencies and add missing devDependencies
  ([#17](https://github.com/PrintQue-ca/PrintQue/pull/17),
  [`4434dea`](https://github.com/PrintQue-ca/PrintQue/commit/4434deae9fd003425c77dd64c13e3763347df303))

### Continuous Integration

- **release workflow**: Add release workflow for cross-platform builds and Discord notification
  ([#19](https://github.com/PrintQue-ca/PrintQue/pull/19),
  [`37fafc8`](https://github.com/PrintQue-ca/PrintQue/commit/37fafc8127943247b5a2e8fc9917612c70d87c4b))

### Refactoring

- Updating for release, minor clean up ([#17](https://github.com/PrintQue-ca/PrintQue/pull/17),
  [`4434dea`](https://github.com/PrintQue-ca/PrintQue/commit/4434deae9fd003425c77dd64c13e3763347df303))

- **root level files**: Cleaning up the root level of the project
  ([#18](https://github.com/PrintQue-ca/PrintQue/pull/18),
  [`4a65a77`](https://github.com/PrintQue-ca/PrintQue/commit/4a65a77c4689acfbc7637344ffa6f55e4d438b65))

- **status_poller.py**: Improve readability of background distribution function
  ([#16](https://github.com/PrintQue-ca/PrintQue/pull/16),
  [`b5cc6c0`](https://github.com/PrintQue-ca/PrintQue/commit/b5cc6c08a7db20df0fdf5345b2195d9095477c8f))

- **status_poller.py**: Refactoring file and helpers for readability
  ([#16](https://github.com/PrintQue-ca/PrintQue/pull/16),
  [`b5cc6c0`](https://github.com/PrintQue-ca/PrintQue/commit/b5cc6c08a7db20df0fdf5345b2195d9095477c8f))


## v1.2.3 (2026-02-07)

### Bug Fixes

- **status_poller.py**: Fix status overrides
  ([#15](https://github.com/PrintQue-ca/PrintQue/pull/15),
  [`e02b768`](https://github.com/PrintQue-ca/PrintQue/commit/e02b7686e72d8e747177ca5580f02d637f263b7d))


## v1.2.2 (2026-02-07)

### Bug Fixes

- **status_poller**: Correct the polling status and release pipeline
  ([#14](https://github.com/PrintQue-ca/PrintQue/pull/14),
  [`e1a36eb`](https://github.com/PrintQue-ca/PrintQue/commit/e1a36eb4b8f91b2a08dc49eefc32c2ab9ab42973))


## v1.2.1 (2026-02-07)

### Bug Fixes

- **status_poller.py**: Keep accurate state of the printer when idle and ready
  ([#13](https://github.com/PrintQue-ca/PrintQue/pull/13),
  [`9cccdb6`](https://github.com/PrintQue-ca/PrintQue/commit/9cccdb6c252f0699426133d530d7517e5d980c5d))

### Continuous Integration

- **version-bump.yml**: Forcing release deployment
  ([#13](https://github.com/PrintQue-ca/PrintQue/pull/13),
  [`9cccdb6`](https://github.com/PrintQue-ca/PrintQue/commit/9cccdb6c252f0699426133d530d7517e5d980c5d))


## v1.2.0 (2026-02-07)

### Bug Fixes

- **ci**: Resolve linting and test failures ([#12](https://github.com/PrintQue-ca/PrintQue/pull/12),
  [`40112cc`](https://github.com/PrintQue-ca/PrintQue/commit/40112cc2970ffe0e37b657fdab2653c0a612b4f9))

### Documentation

- **license update**: Updating license to MIT based on original repository
  ([#11](https://github.com/PrintQue-ca/PrintQue/pull/11),
  [`c469774`](https://github.com/PrintQue-ca/PrintQue/commit/c46977408955df354423a347d0bc5bf1bb12e303))

### Features

- **logging**: Enhance logging setup and improve printer state management
  ([#12](https://github.com/PrintQue-ca/PrintQue/pull/12),
  [`40112cc`](https://github.com/PrintQue-ca/PrintQue/commit/40112cc2970ffe0e37b657fdab2653c0a612b4f9))

- **logging**: Enhance logging setup and improve printer state manage…
  ([#12](https://github.com/PrintQue-ca/PrintQue/pull/12),
  [`40112cc`](https://github.com/PrintQue-ca/PrintQue/commit/40112cc2970ffe0e37b657fdab2653c0a612b4f9))

### Refactoring

- **printer-manager**: Refactor to split as it was 3k
  ([#9](https://github.com/PrintQue-ca/PrintQue/pull/9),
  [`bc6f236`](https://github.com/PrintQue-ca/PrintQue/commit/bc6f2362850833d33d2ee2d27e94b6686b486cd9))


## v1.1.2 (2026-01-27)

### Bug Fixes

- **ci**: Add explicit tag_name for manual workflow dispatch releases
  ([`bc6b624`](https://github.com/Sam-Hoult/PrintQue/commit/bc6b6248ad33d1e4b0e90a646c9df1b67e790da7))


## v1.1.1 (2026-01-26)

### Bug Fixes

- **ci**: Prevent semantic-release from creating GitHub releases
  ([`eecff41`](https://github.com/Sam-Hoult/PrintQue/commit/eecff415df9e69786818b81b99c47cc058a919df))


## v1.1.0 (2026-01-26)

### Chores

- Remove Windows executable signing from release workflow
  ([#8](https://github.com/Sam-Hoult/PrintQue/pull/8),
  [`25f7e48`](https://github.com/Sam-Hoult/PrintQue/commit/25f7e48c0130aa5e0e580496263d7adac9d73b72))

- **readme**: Updating support ([#8](https://github.com/Sam-Hoult/PrintQue/pull/8),
  [`25f7e48`](https://github.com/Sam-Hoult/PrintQue/commit/25f7e48c0130aa5e0e580496263d7adac9d73b72))

### Documentation

- Add Discord community badge and link to README
  ([#8](https://github.com/Sam-Hoult/PrintQue/pull/8),
  [`25f7e48`](https://github.com/Sam-Hoult/PrintQue/commit/25f7e48c0130aa5e0e580496263d7adac9d73b72))

### Features

- Add Windows executable signing and enhance PrinterCard with delete functionality
  ([#8](https://github.com/Sam-Hoult/PrintQue/pull/8),
  [`25f7e48`](https://github.com/Sam-Hoult/PrintQue/commit/25f7e48c0130aa5e0e580496263d7adac9d73b72))

### Testing

- **printercard**: Fix failed test mock ([#8](https://github.com/Sam-Hoult/PrintQue/pull/8),
  [`25f7e48`](https://github.com/Sam-Hoult/PrintQue/commit/25f7e48c0130aa5e0e580496263d7adac9d73b72))


## v1.0.0 (2026-01-25)

- Initial Release

## v1.0.0 (2026-01-25)

- Initial Release
