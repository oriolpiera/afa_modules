# School courses and year-end promotion

Install `afa_school_course` after the family, membership, and monthly service
addons. A family manager defines the courses under
**AFA Families → Configuration → School Courses**. Give each course a distinct
sequence and select its successor; leave the final course without a successor.
Assign a course to every active student on the student contact or the family
form.

For the usual ladder, open
**AFA Families → Configuration → Quick Course Setup**, tick preschool
(i3, i4, i5), primary (1r to 6è) and secondary (1r ESO to 4t ESO), and confirm.
The wizard creates the missing courses, orders them by sequence and links each
course to its successor, including stage boundaries when more than one stage is
selected (i5 → 1r and 6è → 1r ESO). The last course of the last selected stage
stays without a successor, which means graduation; a successor that is already
configured is kept. Existing courses are reused: only missing courses and empty
successors are filled in, the wizard refuses to run when a sequence or an
existing link would have to change, and it also refuses when the result would
leave the courses in more than one ladder. Select the stages that continue the
existing courses together with the new ones.

From June onwards, open
**AFA Families → Configuration → Promote Students**, select the school year
that is ending or has just ended, and refresh the preview. The wizard shows all
active students and their next
course. An empty next course means graduation. Confirmation advances all active
students with no exceptions. Graduates are withdrawn from this year's services
before their contact is archived; their family, invoices, and subscription
history are preserved. Other years' services remain unchanged.

Configure a valid open leave window for every graduate subscription that has
not yet been withdrawn. If a window is missing, a graduate has a subscription
in a later school year, a future charge prevents a withdrawal, or a student has
no course, the entire promotion is refused. Cancel incompatible future invoices
through the existing service billing workflow and
refresh the preview before retrying. Since leave windows close by June 30,
complete service withdrawals before the selected year ends. Archived graduates
cannot enroll in new services. A completed year cannot be promoted twice.
