select sa4_code, month, count(*) as row_count
from {{ ref('stg_sa4_labour') }}
group by 1, 2
having count(*) > 1
