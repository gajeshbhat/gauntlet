Feature: Gates hold for every supported language
  Coverage, complexity and exclusion checks are the same for each language; a language cannot hide code from them.

  @test(tests/test_clean.py::test_a_source_file_the_report_never_mentions_counts_as_uncovered)
  Scenario: A source file the coverage report never mentions is uncovered
    Given a project with two source files
    When the coverage report names only one of them
    Then the other file's functions count as 0% covered

  @test(tests/test_clean.py::test_a_report_matching_no_source_file_is_an_error_not_a_pass)
  Scenario: A report that names none of the project's files is an error
    Given a coverage report for other files
    When the clean gate reads it
    Then it refuses with an error instead of passing

  @test(tests/test_clean.py::test_a_function_with_branches_but_no_measured_lines_counts_as_uncovered)
  Scenario: A branching function with no measured lines is not trivially covered
    Given a function with branches that the report gives no lines
    When the clean gate scores it
    Then it counts as 0% covered

  @test(tests/test_clean.py::test_a_test_looking_name_inside_the_source_tree_is_still_checked)
  Scenario: Only the top-level test directory is exempt
    Given a file named like a test inside the source tree
    When the clean gate walks the project
    Then it is held to the CRAP limit like any source file

  @test(tests/test_linecov.py::test_go_profile_refuses_implausible_blocks)
  Scenario: A hostile Go coverage profile is refused
    Given a profile block that runs backwards or expands to millions of lines
    When the profile is read
    Then reading fails instead of expanding it

  @test(tests/test_exclusions.py::test_config_hints_find_settings_that_can_hide_code)
  Scenario: Build settings that can hide code are reported
    Given a project with a coverage-affecting settings file
    When the exclusions gate scans it
    Then the file is listed as a config exclude

  @test(tests/test_cli.py::test_run_checks_cpp_coverage_and_says_harden_was_skipped)
  Scenario: A language without a mutation tool fails unless the operator accepts it
    Given a C++ project and a default policy
    When gauntlet runs
    Then harden is reported as skipped and the run fails

  @test(tests/test_scaffold.py::test_init_writes_a_config_for_every_other_language)
  Scenario: Init detects every supported language
    Given a project with a language's marker file
    When gauntlet init runs
    Then it writes a gauntlet.toml that loads
