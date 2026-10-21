# AFA Apparel Shop

`afa_apparel_shop` adds a seven-day stock reservation to website orders paid by
bank transfer. It uses Odoo product variants, Inventory, the existing AFA member
pricelists, and the built-in Wire Transfer payment provider. Orders are collected
at the school using a zero-cost pickup delivery method.

## Production setup

1. Install `afa_apparel_shop`, configure one warehouse on the website, and enable
   stock tracking for the apparel products. Set **Sell when Out-of-Stock** to
   off so customers cannot order a size that is unavailable. Set the warehouse's
   Delivery Orders reservation method to **At Confirmation**.
2. Create these products as goods with the **Size** attribute. Set the public
   price on the product and add a fixed-price rule for each product to the AFA
   member pricelist:

   - **Jaqueta Xandall NOU MODEL** — sizes 2, 4, 6, 8, 10, 12, S, M, L;
     member €30, non-member €35.
   - **Samarreta màniga curta** — sizes 3-4, 5-6, 7-8, 9-10, 11-12, S, M, L;
     member €12, non-member €15.
   - **Samarreta màniga llarga** — sizes 3-4, 5-6, 7-8, 9-10, 11-12, S, M, L;
     member €15, non-member €18.

   `afa_member_pricing` applies the member price to identified guardians whose
   family membership is active. Other customers see the non-member price. The
   prices and products in addon demo data are test fixtures; create the live
   catalog in the production database.
3. Enter the starting quantity for every size through **Inventory → Operations →
   Physical Inventory**. Future counts and corrections can be applied there as
   well. Inventory is tracked per variant, so each size has its own on-hand count.
4. Configure the Wire Transfer payment provider with the AFA bank details. Set
   its communication to the sales-order reference and tell families to include
   that reference in the transfer subject. Configure a zero-cost **Recollida a
   l'escola** delivery method for the website.

## Order and stock flow

- At Wire Transfer checkout, Odoo places the order in **Quotation Sent**. This
  addon reserves the selected variants for seven days and shows the deadline on
  the sales order.
- The website and other sales-order confirmations subtract active website
  reservations from available stock. Concurrent orders cannot reserve the same
  remaining unit.
- After matching the bank transfer, staff confirm the sales order. Odoo then
  takes over with its normal stock delivery flow; the family collects the order
  at school.
- An hourly scheduled action cancels unpaid orders after their reservation
  deadline and releases their sizes. Expired orders cannot be confirmed.
- This reservation applies only to the built-in Wire Transfer provider. A later
  online payment provider can use Odoo's normal successful-payment and stock
  confirmation flow.

## Local tests

Use a new database name and inspect Odoo's test summary, not only the process exit
code:

```sh
docker compose -f compose.test.yaml run --rm -e AFA_EXPECT_DEMO=1 odoo -d afa_apparel_shop_fresh_example -i afa_family,afa_membership,afa_member_pricing,afa_apparel_shop --with-demo --test-enable --test-tags /afa_apparel_shop --stop-after-init --log-level=test --db_host=db --db_user=odoo --db_password=odoo
```
