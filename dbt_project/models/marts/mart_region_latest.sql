with ordered as (
    select
        *,
        lag(unemp_rate, 3) over (partition by sa4_code order by month) as rate_three_months_ago,
        row_number() over (partition by sa4_code order by month desc) as recency
    from {{ ref('stg_sa4_labour') }}
)
select
    sa4_code,
    sa4_name,
    state_code,
    state_name,
    month as latest_month,
    unemp_rate,
    participation_rate,
    labour_force,
    unemp_rate - rate_three_months_ago as change_over_three_months
from ordered
where recency = 1
