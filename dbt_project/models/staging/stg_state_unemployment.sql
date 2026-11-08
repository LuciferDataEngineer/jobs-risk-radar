select
    region_code,
    region_name,
    cast(month as date) as month,
    unemp_rate_sa
from read_parquet('{{ env_var("JRR_ROOT") }}/data/snapshot/state_unemployment.parquet')
