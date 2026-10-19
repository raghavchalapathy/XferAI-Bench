# Field dictionary

Canonical logical tables. Customer files may use other column names; map them in
`metadata.json` under `tables.<table>.columns` (canonical name -> source column).
IDs are always strings. Dates are ISO `YYYY-MM-DD` local dates in the declared timezone.
In CSV an empty cell is null; nulls are never converted to zero.

## `observations` (required)

One row per offered item-location week with measured sales or an explicit missing record.

Primary key: `item_id, fpg_id, week_start`.

Join cardinality: Each row joins exactly one offers row with offer_state='offered'.

| Column | Type | Required | Nullable | Unit | Allowed | Meaning |
|---|---|---|---|---|---|---|
| `item_id` | string | yes | no |  |  | Stable item identifier, preserved as a string. |
| `fpg_id` | string | yes | no |  |  | Forecast Pixel Group (company demand area) identifier. |
| `week_start` | date32[day] | yes | no |  |  | Inclusive interval start (declared week boundary). |
| `week_end` | date32[day] | yes | no |  |  | Exclusive interval end; week_start + 7 days. |
| `units` | double | yes | yes | item_units |  | Observed unit sales; null only when observation_state='missing'. Zero is a real observation. |
| `observation_state` | string | yes | no |  | observed, observed_censored, missing | observed | observed_censored (stock-limited sales) | missing (no measurement). |
| `known_at` | date32[day] | yes | no |  |  | Date the measurement became available (reporting delay). |

## `offers` (required)

Offer and availability calendar per pair-week. Absence of a row means never offered.

Primary key: `item_id, fpg_id, week_start`.

Join cardinality: At most one row per pair-week; observations are a subset of offered rows.

| Column | Type | Required | Nullable | Unit | Allowed | Meaning |
|---|---|---|---|---|---|---|
| `item_id` | string | yes | no |  |  |  |
| `fpg_id` | string | yes | no |  |  |  |
| `week_start` | date32[day] | yes | no |  |  |  |
| `week_end` | date32[day] | yes | no |  |  |  |
| `offer_state` | string | yes | no |  | offered, not_offered |  |
| `offered_days` | int64 | yes | no | days |  | Days in the interval the item was offered (0-7). |
| `available_days` | int64 | yes | yes | days |  | Days with sellable stock; null when unknown. |
| `exposure_fraction` | double | yes | no | fraction |  | offered_days / 7. |
| `stockout_state` | string | yes | no |  | in_stock, stockout, unknown |  |
| `known_at` | date32[day] | yes | no |  |  | Date the realized availability became known. |

## `items` (required)

Item attributes, versioned by effective_from/known_at.

Primary key: `item_id, effective_from`.

| Column | Type | Required | Nullable | Unit | Allowed | Meaning |
|---|---|---|---|---|---|---|
| `item_id` | string | yes | no |  |  |  |
| `category` | string | yes | yes |  |  | Category (seasonality level); null means unknown. |
| `product_type` | string | yes | yes |  |  | Product type (broadest hierarchy level). |
| `subcategory` | string | no | yes |  |  | Subcategory (finest group level of the rate fallback hierarchy). |
| `seasonality_class` | string | no | yes |  |  | Declared business class, e.g. seasonal or replenishable. |
| `effective_from` | date32[day] | yes | no |  |  |  |
| `known_at` | date32[day] | yes | no |  |  |  |

## `locations` (required)

FPG attributes including household exposure and demographic shares, versioned.

Primary key: `fpg_id, effective_from`.

Additional columns with prefixes ['share_'] are declared in metadata (e.g. demographic share columns).

| Column | Type | Required | Nullable | Unit | Allowed | Meaning |
|---|---|---|---|---|---|---|
| `fpg_id` | string | yes | no |  |  |  |
| `region` | string | yes | yes |  |  |  |
| `fpg_open_at` | date32[day] | yes | yes |  |  | Date the FPG began trading; null if before history. |
| `households` | double | yes | no | households |  | Non-overlapping serviceable households (H). |
| `effective_from` | date32[day] | yes | no |  |  |  |
| `known_at` | date32[day] | yes | no |  |  |  |

## `launches` (required)

Natural (or explicitly simulated) first-offer events of an existing item at a location.

Primary key: `launch_id`.

| Column | Type | Required | Nullable | Unit | Allowed | Meaning |
|---|---|---|---|---|---|---|
| `launch_id` | string | yes | no |  |  |  |
| `pair_id` | string | yes | no |  |  |  |
| `item_id` | string | yes | no |  |  |  |
| `fpg_id` | string | yes | no |  |  |  |
| `first_offer_at` | date32[day] | yes | no |  |  | Exact first offer date. |
| `first_offer_week` | date32[day] | yes | no |  |  | Week start containing first_offer_at. |
| `fpg_open_at` | date32[day] | yes | yes |  |  |  |
| `origin` | date32[day] | yes | no |  |  | Cold forecast origin; equals first_offer_week (no interim pair sales). |
| `scenario` | string | yes | no |  | PAIR0-E, PAIR0-N |  |
| `qualification` | string | yes | no |  | qualified, edge_fixture, disqualified |  |
| `launch_type` | string | yes | no |  | natural, simulated |  |
| `cohort_id` | string | yes | no |  |  |  |
| `fixture_kind` | string | no | yes |  |  | Edge-fixture label (partial_week, stockouts, missing_targets, ...). |

## `origin_features` (optional)

Origin snapshots of company features (e.g. propensity P, item rank, item-cluster affinity).

Primary key: `feature_name, scope, item_id, fpg_id, scope_id, origin`.

| Column | Type | Required | Nullable | Unit | Allowed | Meaning |
|---|---|---|---|---|---|---|
| `feature_name` | string | yes | no |  |  |  |
| `scope` | string | yes | no |  | pair, item, location, category, global |  |
| `item_id` | string | yes | yes |  |  |  |
| `fpg_id` | string | yes | yes |  |  |  |
| `scope_id` | string | yes | yes |  |  |  |
| `origin` | date32[day] | yes | no |  |  |  |
| `value` | double | yes | yes |  |  |  |
| `unit` | string | yes | no |  |  |  |
| `known_at` | date32[day] | yes | no |  |  |  |
| `source_version` | string | yes | no |  |  |  |

## `donors` (optional)

Optional pre-aggregated national/donor item series with household coverage.

Primary key: `item_id, donor_scope_id, week_start`.

| Column | Type | Required | Nullable | Unit | Allowed | Meaning |
|---|---|---|---|---|---|---|
| `item_id` | string | yes | no |  |  |  |
| `donor_scope_id` | string | yes | no |  |  |  |
| `week_start` | date32[day] | yes | no |  |  |  |
| `week_end` | date32[day] | yes | no |  |  |  |
| `units` | double | yes | yes | item_units |  |  |
| `household_coverage` | double | yes | no | household_weeks |  |  |
| `known_at` | date32[day] | yes | no |  |  |  |
| `source_version` | string | yes | no |  |  |  |

## `future_covariates` (optional)

Inputs about future weeks that were genuinely known/planned/issued at origin.

Primary key: `feature_name, item_id, fpg_id, scope_id, origin, forecast_week`.

| Column | Type | Required | Nullable | Unit | Allowed | Meaning |
|---|---|---|---|---|---|---|
| `feature_name` | string | yes | no |  |  |  |
| `item_id` | string | yes | yes |  |  |  |
| `fpg_id` | string | yes | yes |  |  |  |
| `scope_id` | string | yes | yes |  |  |  |
| `origin` | date32[day] | yes | no |  |  |  |
| `forecast_week` | date32[day] | yes | no |  |  |  |
| `value` | double | yes | yes |  |  |  |
| `availability_class` | string | yes | no |  | calendar, planned, forecast, scenario |  |
| `known_at` | date32[day] | yes | no |  |  |  |
| `source_version` | string | yes | no |  |  |  |
