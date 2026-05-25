# Upstream reproduction scripts

Minimal scripts for reporting bugs to dependencies. **Not** part of the Zensical docs site.

| Script | Upstream | Purpose |
|--------|----------|---------|
| [ferro-enum-hydration-repro.py](ferro-enum-hydration-repro.py) | [ferro-orm](https://github.com/syn54x/ferro-orm) | TTD consumer: cold fetch → `str` instead of `StrEnum` |
| [ferro-enum-hydration-repro-standalone.py](ferro-enum-hydration-repro-standalone.py) | ferro-orm | Same bug, no TTD imports |

Fixed in ferro-orm **≥ 0.10.5** ([PR #66](https://github.com/syn54x/ferro-orm/pull/66), [issue #65](https://github.com/syn54x/ferro-orm/issues/65)). TTD pins `ferro-orm>=0.10.5`.

Scripts below fail on **0.10.3** and pass on current ferro; keep for regression checks. Upstream repro text lives in the issue body, not here.
