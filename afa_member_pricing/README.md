# AFA Member Pricing

`afa_member_pricing` applies native Odoo pricelists to family sales and the shop.
It depends on `afa_membership`, `sale`, and `website_sale`. It does not create
duplicate products or override the native product/variant/category rule engine.

## Configure

1. Enable pricelists in Sales settings and create a member and a non-member
   pricelist in the **same currency** for the **same website**. Set both to the
   sales company; the member pricelist must have neither **Selectable** nor a
   promotional code. The non-member pricelist can be selectable.
2. Add native pricelist items for products, variants, categories, or services.
   Other products use Odoo's standard fallback price.
3. Under Settings → AFA Pricing, assign both pricelists to the company. Both
   must be configured together; an unconfigured company uses standard Odoo
   pricing. The family billing guardian must be linked to `afa.family`.

## Pricing and checkout

An identified guardian with an active family membership receives the member
pricelist. Other customers and anonymous visitors receive the non-member
pricelist. The family shown on the sale order is derived from the customer;
staff do not choose an unrelated family. Changing the customer or pricelist on
an open quotation updates its existing lines. Confirmed orders keep their
agreed prices, even if membership subsequently changes.
Manually agreed line prices and discounts survive a quotation repricing; native
discount rules are recalculated. If membership changes on an open backend
quotation, staff must select the newly applicable pricelist before confirming
it. Confirmation refuses a stale member tariff rather than silently changing
the agreed order.

The website uses the same assigned pricelist for product pages and carts.
The member pricelist cannot be selected through the public selector or promo
endpoint. Reopening a cart recalculates it if eligibility has changed. The
payment gate rejects a stale cart before creating a transaction: return to
the cart to review the new price. Membership is checked at these boundaries
rather than on every cart update.

## Verify locally

An installation **with demo data** configures EUR pricelists on the default
website and publishes two products: **Xandall** (S/M/L, member €25,
non-member €35) and **Samarreta màniga curta** (S/M/L, member €12,
non-member €15). Each product has three native variants and one native rule
per product and pricelist. Demo data does not change the membership mode or
grant membership to demo families; set membership according to the manager
workflow to see the member price.

Use an unused database name; inspect the Odoo test result summary, not just
the command exit status:

```sh
docker compose -f compose.test.yaml run --rm -e AFA_EXPECT_DEMO=1 odoo -d afa_pricing_fresh_example -i afa_family,afa_membership,afa_member_pricing --with-demo --test-enable --test-tags /afa_member_pricing --stop-after-init --log-level=test --db_host=db --db_user=odoo --db_password=odoo
```
