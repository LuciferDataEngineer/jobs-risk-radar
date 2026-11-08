select
    sa4_code,
    sa4_name,
    state_code,
    state_name,
    cast(month as date) as month,
    employed,
    unemployed,
    nilf,
    labour_force,
    unemp_rate,
    participation_rate,
    youth_unemp_rate
from read_parquet('{{ env_var("JRR_ROOT") }}/data/snapshot/sa4_month.parquet')
