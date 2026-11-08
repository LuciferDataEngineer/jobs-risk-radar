select
    region_code,
    region_name,
    cast(month as date) as month,
    dwelling_approvals
from read_parquet('{{ env_var("JRR_ROOT") }}/data/snapshot/approvals.parquet')
