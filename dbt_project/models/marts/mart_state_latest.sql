with ordered as (
    select
        *,
        lag(unemp_rate_sa, 12) over (partition by region_code order by month) as rate_year_ago,
        row_number() over (partition by region_code order by month desc) as recency
    from {{ ref('stg_state_unemployment') }}
)
select
    region_code,
    region_name,
    month as latest_month,
    unemp_rate_sa,
    rate_year_ago,
    unemp_rate_sa - rate_year_ago as change_over_year
from ordered
where recency = 1
