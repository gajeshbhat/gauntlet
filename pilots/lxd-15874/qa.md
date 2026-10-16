# QA procedure (human-readable; automated as test/suites/container_devices_disk.sh `_container_devices_disk_propagation`)

Environment: the `v1` VM, LXD built from the branch, `./test/main.sh container_devices_disk`.

1. Make a host directory a shared mount: `mount --bind D D && mount --make-rshared D`.
2. Launch a container (unprivileged, then `security.privileged=true`).
3. `lxc config device add c prop disk source=D path=/mnt/prop propagation=rshared`.
4. In the container: `mount -t tmpfs tmpfs /mnt/prop && touch /mnt/prop/marker`.
5. Expect `D/marker` to exist on the host. Without the fix it does not.
6. On the host, mount a tmpfs at `D/hostmnt` and touch a file there; expect it visible at `/mnt/prop/hostmnt/` in the container.
7. With no `propagation` key, repeat 4: expect `D/marker` NOT to exist (default unchanged).
