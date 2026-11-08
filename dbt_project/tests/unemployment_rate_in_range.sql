select sa4_code, month, unemp_rate
from {{ ref('stg_sa4_labour') }}
where unemp_rate < 0 or unemp_rate > 40
