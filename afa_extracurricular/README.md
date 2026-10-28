# Extracurricular activities

Staff define extracurricular activities per school year with an informative
registration period, monthly member/non-member fees, groups, weekly schedules and
informational seats, and enroll students into one group per activity. This addon
depends on `afa_service_subscription` and `afa_school_course`; it reuses the
subscription change windows, monthly billing and family invoicing, and adds no
portal or web self-registration.

## Configure

1. Install `afa_extracurricular` and give staff the **AFA Family Manager** group.
2. Open **AFA Families → Extracurriculars** and create an activity. It is a
   monthly service, so choose the school year, the execution period as complete
   months (for example October 1 to May 31), a saleable product and the monthly
   member/non-member prices. Set the **informative enrollment period** (for
   example September 10 to 20): it is shown for orientation only and never blocks
   an enrollment.
3. Add groups on the **Groups** tab. Give each group a unique name within the
   activity, an informational seat count and its weekly schedule (weekdays and a
   time range, for example Monday and Wednesday 12:30–13:30).

## Enroll

1. Open the activity and click **Enrollments**, then create a subscription. The
   service and the join window domain come from the activity, and the **group** is
   mandatory while the activity's join window is open; effective membership rules
   belong to the reusable subscription, not to the activity's informative dates.
2. The same enrollment list is reachable from the **student** and the **family**
   forms through their **Extracurriculars** buttons. A student can be in zero, one
   or several activities but only one group per activity; two subscriptions to the
   same activity are rejected by the reusable service subscription rules.
3. Request a withdrawal on the subscription as usual. Informational seat counts
   never block an enrollment, and overlapping schedules across activities are
   allowed and shown as information only.

## Import enrollments

Family managers can use **AFA Families → Configuration → Import Enrollments**
to load a CSV with one row per student and activity. The required columns are
`curs,nen,extraescolar,grup`; `telefon` is optional and shown for review only.
For example:

```csv
curs,nen,telefon,extraescolar,grup
i4,Joan,666666666,Manualitats,Dilluns 12:30
3r,Maria,555555555,Manualitats,Dilluns 13:30
i5,Marc,111111111,Circ,Dimarts 12:30
```

Students are matched by name and school course. Activities must have an open join
window, and each group value must exactly match a group name within that activity.
Create students, activities, and groups before importing; the importer only
creates enrollments. It previews every row first, reports ambiguous or missing
matches and conflicting enrollments, and blocks confirmation while errors remain.
An enrollment already assigned to the same group is skipped. The existing
subscription flow remains responsible for family, join-window, and billing rules.

## Bill

Use the monthly billing review from `afa_service_subscription`: refresh a month in
**AFA Families → Collections → Monthly Service Billing**. Charge only months
inside the activity's execution period, using the family's member tariff for
that month, and generate one draft invoice per family and month. Repeating the
preview and confirmation never duplicates charges. The addon does not track
routine attendance; it records only sessions canceled because the instructor is
unavailable.

## Canceled sessions

Before generating invoices for a month, a family manager can record a canceled
session in its group's **Canceled Sessions** list. Each record identifies the
session date and a per-student discount, defaulting to €5 and editable by the
manager. A group can have only one cancellation record per date. The date must
fall within the activity's execution period.

Monthly billing applies each recorded discount to every enrolled student in that
group for the month of the session. It subtracts the combined discounts from the
full tariff and floors the remaining charge at €0; excess is not carried forward.
For scholarship families, the Council and family shares are recalculated from
the discounted tariff using the configured percentage. The preview displays the
tariff and discount before invoices are generated.

Once a month's invoices have been generated, its cancellation records cannot be
added, edited, or removed. Late cancellations must be handled manually; they do
not automatically change existing invoices.

## Scholarships

On a family record, configure at most one extracurricular scholarship per school
year with its Council Comarcal sponsor, the percentage paid by the Council, and the
tariff basis. Choose either the family's effective membership tariff or the member
tariff regardless of actual membership. Using the member tariff does not change the
family's membership status.

Monthly billing shows the full tariff and the split. It creates a family invoice for
the remaining amount and a separate invoice to the Council for that family and month.
Council invoices use the activity sales journal and are not assigned the family's
direct-debit payment mode. If either invoice is canceled, cancel its paired invoice
before regenerating the charge. The original charge records preserve both amounts
and the tariff/subsidy settings used for that billing month.

Run the Odoo 19 test stack as described in the repository README, including
`afa_extracurricular` in the installation list and `/afa_extracurricular` in
`--test-tags`.
