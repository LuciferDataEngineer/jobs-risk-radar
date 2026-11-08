select
    cast(month as date) as month,
    cash_rate_target
from read_parquet('{{ env_var("JRR_ROOT") }}/data/snapshot/cash_rate_month.parquet')
