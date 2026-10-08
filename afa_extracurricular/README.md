# Extracurricular activities

Staff define extracurricular activities per school year with an informative
registration period, monthly member/non-member fees, groups, weekly schedules and
informational seats, and enroll students into one group per activity. This addon
depends on `afa_service_subscription` and reuses its change windows, monthly
billing and family invoicing; it adds no portal or web self-registration.

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

## Bill

Billing is unchanged from `afa_service_subscription`: refresh a month in
**Monthly Service Billing**, charge only months inside the activity's execution
period with the member tariff of the family for that month, and generate one
draft invoice per family and month. Repeating the preview and confirmation never
duplicates charges. Scheduled activities need no attendance control.

Run the Odoo 19 test stack as described in the repository README, including
`afa_extracurricular` in the installation list and `/afa_extracurricular` in
`--test-tags`.