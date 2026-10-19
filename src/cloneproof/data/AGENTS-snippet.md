## Matching a reference website (cloneproof)

When the task is to clone, rebuild or restyle a site so it matches a reference, use `cloneproof`
instead of eyeballing: `cloneproof compare <original> <clone> --json --target 97`. Fix the
issues it lists (biggest first) in the source code, then run it again until it exits 0 or two rounds
do not improve. See the `cloneproof` skill for details. Install: `pip install git+https://github.com/pcjansen09-max/cloneproof && cloneproof doctor`.
