# Family load assistant delta specification

## ADDED requirements

### Requirement: The wizard loads a CSV/Excel file into complete families
A family manager SHALL be able to upload a CSV or `.xlsx` file whose rows describe people, grouped by a shared family name, and create the corresponding families. Each row SHALL carry `family_name`, `role`, `name` and MAY carry `is_billing`, `email`, `phone`, `course`, `iban` and `mandate_date`. Headers SHALL be matched case-insensitively and with whitespace or spaces normalised to underscores.

For each new family the system SHALL create the people in this order: the billing guardian without a family, then the `afa.family` linked to it, then the remaining guardians and students, then a `res.partner.bank` for every row carrying an IBAN, then, for the billing guardian and only when enabled, a SEPA Core recurrent mandate.

#### Scenario: A complete file creates one family
- **GIVEN** courses exist and the file contains two guardian rows and one student row sharing a family name, with the first guardian marked as billing
- **WHEN** the manager loads the file and confirms
- **THEN** one family is created whose billing partner is the first guardian, the other people are linked to it with their roles, and the student holds the named course.

#### Scenario: The billing guardian is created without a family first
- **WHEN** a family is created through the wizard
- **THEN** the payer is a guardian of that same family, satisfying the family billing invariant, and no partner is duplicated.

#### Scenario: Exactly one guardian is auto-designated
- **GIVEN** a family has one guardian and no `is_billing` marker
- **WHEN** the file is validated
- **THEN** that guardian becomes the billing guardian and the family imports.

### Requirement: The wizard validates before writing and previews errors per row
The system SHALL validate the whole file before any record is created and SHALL show the reason on each offending row. A role SHALL be `guardian` or `student`; a student SHALL carry a course that already exists; a course SHALL never be assigned to a non-student; an email SHALL be well formed; an IBAN SHALL contain only ASCII letters and digits, pass an ISO 13616 mod-97 check and a known country length; a mandate signature date SHALL not be in the future. A family SHALL have at least one guardian, the billing guardian SHALL be one of those guardians, and a family SHALL NOT have more than one billing guardian. A recognised column that appears twice in the header SHALL be refused rather than silently overwritten.

#### Scenario: An unknown course is refused
- **WHEN** a student row names a course that does not exist
- **THEN** the row is reported with an error and nothing is created.

#### Scenario: Two billing guardians are refused
- **WHEN** two guardian rows of the same family are marked as billing
- **THEN** both rows are reported and the family is not created.

#### Scenario: A student cannot be the billing guardian
- **GIVEN** a family has a guardian and a student marked as billing
- **WHEN** the file is validated
- **THEN** the student row is reported, the guardian is not silently made the payer by omission, and the family is not created.

#### Scenario: A family with no guardian is refused whatever the markers say
- **WHEN** a file contains only student rows for a family, even with a billing marker
- **THEN** the family is reported as needing a guardian and nothing is created.

#### Scenario: An invalid IBAN or future mandate date is refused
- **WHEN** a billing guardian row carries an IBAN failing mod-97 or a mandate date after today
- **THEN** the row is reported and no bank account or mandate is created.

#### Scenario: Repeated columns are refused
- **WHEN** a file header names the same recognised column twice, for example `email` and `Email`
- **THEN** the upload is refused instead of the later cell overwriting the earlier one.

### Requirement: Confirmation is atomic per family and safe to re-run
Confirmation SHALL create each family inside a database savepoint so that a failure affects only that family, and SHALL report the failed family while still importing the rest. The assistant SHALL stay open showing the reasons whenever at least one family failed, and SHALL close only once every family imported. A family whose name already exists, including archived families, SHALL be skipped and reported rather than updated or duplicated, and two confirmations of the same family name SHALL NOT both create it. Only an explicit family manager SHALL be able to load a file or confirm an import.

#### Scenario: One invalid family does not discard the others
- **GIVEN** a file contains a valid family followed by a family that fails creation
- **WHEN** the manager confirms the import
- **THEN** the first family exists, the second is reported as failed, no partial record of the second family remains, and the assistant stays open with the reasons on screen.

#### Scenario: The assistant closes only when everything imported
- **WHEN** every family in the file is created
- **THEN** the assistant closes.

#### Scenario: Re-running the same file is safe
- **GIVEN** a file was imported
- **WHEN** the manager loads and confirms the same file again
- **THEN** the existing family is skipped, reported as such, and no duplicate family, partner, bank account or mandate is created.

#### Scenario: Concurrent confirmation of the same family name is serialised
- **GIVEN** two assistants validated a file naming the same new family
- **WHEN** both confirm at the same time
- **THEN** only one family is created and the other assistant reports it as existing.

#### Scenario: A staff user cannot load a file
- **WHEN** a user without the family-manager group loads a file or confirms an import
- **THEN** the action is denied.

### Requirement: A CSV template is downloadable
The wizard SHALL offer a downloadable CSV template containing the expected header row and example rows that show a billing guardian, a second guardian and a student with a course.

#### Scenario: Template download
- **WHEN** a family manager opens the assistant and requests the template
- **THEN** a CSV file is returned containing the documented header.
