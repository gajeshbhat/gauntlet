Feature: Gates hold for Python
  Coverage, complexity and exclusion checks cannot be dodged by hiding code from them.

  @test(packages/gauntlet-core/tests/test_clean.py::test_a_source_file_the_report_never_mentions_counts_as_uncovered)
  Scenario: A source file the coverage report never mentions is uncovered
    Given a project with two source files
    When the coverage report names only one of them
    Then the other file's functions count as 0% covered

  @test(packages/gauntlet-core/tests/test_clean.py::test_a_report_matching_no_source_file_is_an_error_not_a_pass)
  Scenario: A report that names none of the project's files is an error
    Given a coverage report for other files
    When the clean gate reads it
    Then it refuses with an error instead of passing

  @test(packages/gauntlet-core/tests/test_clean.py::test_a_function_with_branches_but_no_measured_lines_counts_as_uncovered)
  Scenario: A branching function with no measured lines is not trivially covered
    Given a function with branches that the report gives no lines
    When the clean gate scores it
    Then it counts as 0% covered

  @test(packages/gauntlet-core/tests/test_clean.py::test_a_test_looking_name_inside_the_source_tree_is_still_checked)
  Scenario: Only the top-level test directory is exempt
    Given a file named like a test inside the source tree
    When the clean gate walks the project
    Then it is held to the CRAP limit like any source file

  @test(packages/gauntlet-python/tests/test_excludes.py::test_include_and_omit_settings_that_narrow_coverage_are_exclusions)
  Scenario: Coverage settings that hide code are reported
    Given a project whose coverage config omits files
    When the exclusions gate scans it
    Then the setting is listed as a config exclude

  @test(packages/gauntlet-python/tests/test_scaffold_python.py::test_python_project_with_a_src_layout)
  Scenario: Init detects a Python project
    Given a project with a pyproject.toml
    When gauntlet init runs
    Then it writes a gauntlet.toml that loads
