# Specifier output for canonical/lxd#15874 "disk propagation not working".
# Approval: delegated by the user ("use the gauntlet framework strictly"); reviewable in report.md.
Feature: Disk device mount propagation
  The `propagation` key of a disk device must take effect on the mount the instance sees.

  Background:
    Given a host directory that is a shared mount (as on a systemd host)

  Scenario Outline: Mount made inside the instance reaches the host
    Given a <privilege> container with a disk device on that directory and propagation=<mode>
    When a tmpfs is mounted inside the container at the device path
    Then the host sees the files of that tmpfs under the source directory

    Examples:
      | privilege    | mode    |
      | unprivileged | rshared |
      | privileged   | rshared |
      | unprivileged | shared  |

  Scenario: Default propagation is unchanged
    Given a container with a disk device and no propagation key
    When a tmpfs is mounted inside the container at the device path
    Then the host does not see it
    And a mount made on the host under the source directory is visible in the container

  Scenario Outline: Each propagation mode sets the matching kernel propagation on the mount
    When DiskMount is called with propagation=<mode>
    Then the mount is <state> according to /proc/thread-self/mountinfo

    Examples:
      | mode        | state                |
      |             | a slave              |
      | private     | private              |
      | shared      | shared (a peer)      |
      | slave       | a slave              |
      | unbindable  | unbindable           |
      | rshared     | shared (a peer)      |
      | rslave      | a slave              |
      | rprivate    | private              |
      | runbindable | unbindable           |

  Scenario: Invalid propagation is rejected
    When DiskMount is called with propagation=bogus
    Then it fails with "Invalid propagation mode"
    And nothing is mounted

  Scenario: Read-only is still honoured
    When DiskMount is called with the "ro" option and propagation=rshared
    Then the mount is read-only and shared
