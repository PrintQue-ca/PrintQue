/**
 * Commitlint configuration for enforcing Conventional Commits.
 * This enables automatic semantic versioning based on commit messages.
 *
 * Valid commit types:
 *   feat:     A new feature (triggers MINOR version bump)
 *   fix:      A bug fix (triggers PATCH version bump)
 *   docs:     Documentation only changes
 *   style:    Changes that don't affect code meaning (formatting, etc.)
 *   refactor: Code change that neither fixes a bug nor adds a feature
 *   perf:     Performance improvement (triggers PATCH version bump)
 *   test:     Adding or correcting tests
 *   build:    Changes to build system or dependencies
 *   ci:       Changes to CI configuration
 *   chore:    Other changes that don't modify src or test files
 *
 * Breaking changes:
 *   Add ! after type or include "BREAKING CHANGE:" in footer
 *   Example: feat!: remove deprecated API
 *   This triggers a MAJOR version bump
 *
 * @see https://www.conventionalcommits.org/
 */
export default {
  extends: ['@commitlint/config-conventional'],
  rules: {
    // Enforce lowercase type
    'type-case': [2, 'always', 'lower-case'],
    // Enforce allowed types
    'type-enum': [
      2,
      'always',
      [
        'feat',     // New feature
        'fix',      // Bug fix
        'docs',     // Documentation
        'style',    // Formatting, missing semicolons, etc.
        'refactor', // Code restructuring
        'perf',     // Performance improvements
        'test',     // Adding tests
        'build',    // Build system changes
        'ci',       // CI configuration
        'chore',    // Maintenance tasks
        'revert',   // Revert previous commit
      ],
    ],
    // Subject should not be empty
    'subject-empty': [2, 'never'],
    // Type should not be empty
    'type-empty': [2, 'never'],
    // Max header length
    'header-max-length': [2, 'always', 100],
  },
};
