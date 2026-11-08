select
    region_code,
    region_name,
    quarter,
    cast(quarter_end as date) as quarter_end,
    vacancies_000
from read_parquet('{{ env_var("JRR_ROOT") }}/data/snapshot/vacancies.parquet')
