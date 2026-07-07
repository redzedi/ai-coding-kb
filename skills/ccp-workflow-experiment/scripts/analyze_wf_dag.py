#!/usr/bin/env python3
"""
scripts/analyze_wf_dag.py

Parses a CCP Workflow YAML file, builds a transitive Directed Acyclic Graph (DAG),
and scans VTL/SQL files to identify:
1. Hot Intermediate Tables (written by CTAS, scanned multiple times downstream)
2. Hot Base Raw Tables (scanned multiple times across independent modules)
"""

import sys
import os
import re
import yaml
from collections import defaultdict

def load_workflow_modules(workflow_path):
    """Loads all output modules listed in the workflow YAML."""
    if not os.path.exists(workflow_path):
        print(f"Error: Workflow file not found at {workflow_path}", file=sys.stderr)
        return []
    
    with open(workflow_path, 'r') as f:
        config = yaml.safe_load(f)
    
    # Standard CCP structure
    modules = []
    if 'modules' in config:
        modules = [m['name'] for m in config['modules'] if 'name' in m]
    elif 'workflow' in config and 'tasks' in config['workflow']:
        modules = [t['name'] for t in config['workflow']['tasks'] if 'name' in t]
    else:
        # Fallback for alternative task keys
        modules = list(config.keys())
        
    return modules

def find_vtl_paths_for_module(module_name, workspace_root):
    """Finds all VTL files associated with a given module name."""
    vtl_dir = os.path.join(workspace_root, "ccp-configs", "sql", module_name)
    if not os.path.exists(vtl_dir):
        return []
    
    vtl_files = []
    for f in os.listdir(vtl_dir):
        if f.endswith('.vtl') or f.endswith('.sql'):
            vtl_files.append(os.path.join(vtl_dir, f))
    return vtl_files

def parse_vtl_dependencies(vtl_path, all_modules_set):
    """Parses a VTL/SQL file to detect raw base tables and intermediate tables referenced."""
    dependencies = {
        "raw_tables": set(),
        "intermediate_tables": set()
    }
    
    if not os.path.exists(vtl_path):
        return dependencies

    # Matches qualified schema.table patterns (e.g. ams.keywords, client_view_catalog.aramus.skus)
    raw_table_pattern = re.compile(r'\b([a-zA-Z0-9_]+)\.([a-zA-Z0-9_]+)\b')
    
    try:
        with open(vtl_path, 'r', encoding='utf-8') as f:
            content = f.read()
            
            # Clean VTL comments for clean parsing
            content = re.sub(r'##.*?\n', '\n', content)
            content = re.sub(r'#\*.*?\*#', '', content, flags=re.DOTALL)
            
            # Find schema.table matches
            for schema, table in raw_table_pattern.findall(content):
                schema_lower = schema.lower()
                # Skip system variables/keywords and intermediate schemas
                if schema_lower not in ["client_view_catalog", "temp_ccp", "ccp_execute_schema", "sys", "re", "sql"]:
                    dependencies["raw_tables"].add(f"{schema_lower}.{table.lower()}")
            
            # Find references to other modules inside the workflow (intermediate tables)
            words = re.findall(r'\b[a-zA-Z0-9_]+\b', content)
            for word in words:
                word_lower = word.lower()
                if word_lower in all_modules_set:
                    dependencies["intermediate_tables"].add(word_lower)
                    
    except Exception as e:
        print(f"Error parsing VTL {vtl_path}: {e}", file=sys.stderr)
        
    return dependencies

def analyze_transitive_scans(workflow_path, workspace_root):
    """Builds the transitive DAG and compiles the redundant scan reports."""
    print(f"\n==================================================================")
    print(f" TRANSITIVE WORKFLOW DAG & REDUNDANT SCAN ANALYZER")
    print(f"==================================================================")
    print(f"Workflow: {os.path.basename(workflow_path)}")
    print(f"Workspace Root: {workspace_root}")
    
    modules = load_workflow_modules(workflow_path)
    if not modules:
        print("No modules found in the workflow file.")
        return False
    
    all_modules_set = {m.lower() for m in modules}
    
    # Step-wise mapping of dependencies
    module_dependencies = {}
    base_table_scans = defaultdict(list)
    intermediate_table_scans = defaultdict(list)
    
    for module in modules:
        vtl_files = find_vtl_paths_for_module(module, workspace_root)
        module_deps = {
            "raw_tables": set(),
            "intermediate_tables": set()
        }
        
        for vtl in vtl_files:
            deps = parse_vtl_dependencies(vtl, all_modules_set)
            module_deps["raw_tables"].update(deps["raw_tables"])
            module_deps["intermediate_tables"].update(deps["intermediate_tables"])
            
        module_dependencies[module.lower()] = module_deps
        
        # Track raw base table scans
        for raw in module_deps["raw_tables"]:
            base_table_scans[raw].append(module)
            
        # Track intermediate table scans
        for inter in module_deps["intermediate_tables"]:
            intermediate_table_scans[inter].append(module)

    # --- REPORTING ---
    print(f"\n[1] TOTAL WORKFLOW TRANSITIVE SUMMARY:")
    print(f"------------------------------------------------------------------")
    print(f"Total Workflow Modules Compiled: {len(modules)}")
    print(f"Total Unique Base Raw Tables Scanned: {len(base_table_scans)}")
    print(f"Total Unique Intermediate Tables Scanned: {len(intermediate_table_scans)}")

    print(f"\n[2] HOT INTERMEDIATE TABLES (Avoidable CTAS Rescans):")
    print(f"------------------------------------------------------------------")
    avoidable_intermediate_scans = 0
    hot_intermediate = sorted(intermediate_table_scans.items(), key=lambda x: len(x[1]), reverse=True)
    
    print(f"{'Intermediate Table Name':<45} | {'Reads':<5} | {'Avoidable':<9}")
    print("-" * 68)
    for table, readers in hot_intermediate:
        reads = len(readers)
        avoidable = reads - 1
        avoidable_intermediate_scans += avoidable
        if reads > 1:
            print(f"{table:<45} | {reads:<5} | {avoidable:<9} (⚠️ RESCAN)")
            # Print a few readers
            print(f"    - Scanned by: {', '.join(readers)}")
        else:
            print(f"{table:<45} | {reads:<5} | {avoidable:<9}")
            
    print(f"\nTotal Avoidable Intermediate Table Scans: {avoidable_intermediate_scans}")

    print(f"\n[3] HOT BASE RAW TABLES (Avoidable Base Rescans):")
    print(f"------------------------------------------------------------------")
    avoidable_raw_scans = 0
    hot_raw = sorted(base_table_scans.items(), key=lambda x: len(x[1]), reverse=True)
    
    print(f"{'Base Raw Table Name':<45} | {'Scans':<5} | {'Avoidable':<9}")
    print("-" * 68)
    for table, readers in hot_raw:
        scans = len(readers)
        avoidable = scans - 1
        avoidable_raw_scans += avoidable
        if scans > 1:
            print(f"{table:<45} | {scans:<5} | {avoidable:<9} (⚠️ RESCAN)")
            print(f"    - Scanned by: {', '.join(readers[:4])}" + (f", ... ({scans-4} more)" if scans > 4 else ""))
        else:
            print(f"{table:<45} | {scans:<5} | {avoidable:<9}")
            
    print(f"\nTotal Avoidable Base Table Scans: {avoidable_raw_scans}")

    print(f"\n==================================================================")
    print(f" TOTAL REDUNDANT SCANS ELIMINATION POTENTIAL: {avoidable_intermediate_scans + avoidable_raw_scans} SCANS")
    print(f"==================================================================\n")
    return True

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python3 analyze_wf_dag.py <workflow_yaml_path> <workspace_root_path>")
        sys.exit(1)
        
    analyze_transitive_scans(sys.argv[1], sys.argv[2])
