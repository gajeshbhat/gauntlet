# Specifier output for the security follow-up of canonical/lxd#15874.
# Approval: delegated by the user ("fix the lxd bug with our gauntlet"); design from the review that flagged
# container-to-host mount propagation. Scope: restricted projects only; the default and unrestricted projects are unchanged.
Feature: Restricted projects do not let instances create mounts on the host
  A disk device with propagation=shared or rshared lets mounts made inside the instance appear on the host.
  Only an administrator working outside a restricted project may enable that.

  Background:
    Given a project with restricted=true

  @test(lxd/project/limits/permission_internal_test.go::TestProjectRestrictedDiskPropagation)
  Scenario Outline: Modes that reach the host are rejected in a restricted project (block already forbids every disk)
    Given restricted.devices.disk is <policy>
    When an instance has a disk device with propagation=<mode>
    Then the project check fails with "propagation"

    Examples:
      | policy  | mode    |
      | managed | shared  |
      | managed | rshared |
      | allow   | shared  |
      | allow   | rshared |

  @test(lxd/project/limits/permission_internal_test.go::TestProjectRestrictedDiskPropagationAllowsSafeModes)
  Scenario Outline: Modes that cannot reach the host are still allowed
    Given restricted.devices.disk is allow
    When an instance has a disk device with propagation=<mode>
    Then the project check passes

    Examples:
      | mode        |
      |             |
      | private     |
      | slave       |
      | unbindable  |
      | rprivate    |
      | rslave      |
      | runbindable |

  @test(lxd/project/limits/permission_internal_test.go::TestProjectRestrictedDiskPropagationAppliesToProfiles)
  Scenario: A profile cannot smuggle the mode in
    When a profile has a disk device with propagation=rshared
    Then the project check fails with "propagation"

  @test(lxd/project/limits/permission_internal_test.go::TestProjectRestrictedDiskPropagationIgnoresOtherDevices)
  Scenario: Other devices and the root disk are unaffected
    When an instance has a root disk and a nic device with unrelated keys
    Then the project check passes

  @test(lxd/project/limits/permission_internal_test.go::TestProjectRestrictedDiskPropagationNamesTheDevice)
  Scenario: The error says which device and why
    When an instance has a disk device "data" with propagation=rshared
    Then the error names the device "data" and says mounts would appear on the host

  @test(test/suites/container_devices_disk_restricted.sh)
  Scenario: End to end, a restricted project refuses the device
    Given a restricted project with restricted.devices.disk=allow and a permitted source path
    When I add a disk device with propagation=rshared
    Then the command fails, and propagation=slave succeeds
