import re
import sys
import os

def convert_vtl_to_sql(vtl_path, output_path, client_id, rundate, execution_id, extract_select=True):
    if not os.path.exists(vtl_path):
        print(f"Error: VTL file not found at {vtl_path}")
        return False
        
    with open(vtl_path, 'r', encoding='utf-8') as f:
        content = f.read()
        
    sql = content
    sql = sql.replace(":client_id", str(client_id))
    sql = sql.replace(":rundate", str(rundate))
    
    # Replace intermediate tables with fully qualified ephemeral table paths
    intermediate_tables = [
        'competition_look_back',
        'competitive_sku_look_back',
        'comp_skus_from_client_search_list'
    ]
    
    for table in intermediate_tables:
        qualified_table = f"client_view_catalog.temp_ccp_{client_id}.e{execution_id}__{table}"
        sql = re.sub(rf'\b{table}\b', qualified_table, sql)
        
    # Fully qualify aramus / ARAMUS tables with client_view_catalog
    sql = re.sub(r'\b(aramus|ARAMUS)\.(\w+)\b', r'client_view_catalog.aramus.\2', sql)
    
    # Convert all table names in client_view_catalog.aramus. to lowercase for safety
    sql = re.sub(r'client_view_catalog\.aramus\.\w+', lambda m: m.group(0).lower(), sql)
    
    # Extract the SELECT query if wrapped inside a CREATE TABLE ... AS () statement
    if extract_select:
        match = re.search(r'CREATE\s+TABLE\s+\w+\s+AS\s*\(\s*(.*)\s*\)\s*;?\s*$', sql, re.IGNORECASE | re.DOTALL)
        if match:
            sql = match.group(1).strip()
        else:
            match_simple = re.search(r'CREATE\s+TABLE\s+\w+\s+AS\s*\(\s*(.*)\s*\)', sql, re.IGNORECASE | re.DOTALL)
            if match_simple:
                sql = match_simple.group(1).strip()
                
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(sql)
        
    print(f"Successfully converted {vtl_path} to {output_path}")
    return True

if __name__ == '__main__':
    if len(sys.argv) < 6:
        print("Usage: python vtl_to_sql.py <vtl_path> <output_path> <client_id> <rundate> <execution_id>")
        sys.exit(1)
    convert_vtl_to_sql(sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5])
