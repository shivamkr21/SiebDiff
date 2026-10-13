"""How the Siebel repository tables relate to each other.

Every workspace-enabled table has a unique index <TABLE>_U1 that starts with either
REPOSITORY_ID (a top-level object such as an applet) or the column pointing at its
parent (BUSCOMP_ID on S_FIELD). That index is read from the database at run time;
this module only supplies what the index cannot say: which table a parent column
points to, and the Siebel Tools name of each object type.
"""
import re

_IDENT = re.compile(r"^[A-Z][A-Z0-9_$#]*$")
_NOT_PARENT = {"REPOSITORY_ID", "NAME", "WS_ID", "WS_OBJ_VER", "CONFLICT_ID"}

# Parent column -> parent table.
PARENT_BY_COLUMN = {
    "ACCELERATOR_ID": "S_ACCELERATOR", "APLT_TM_VAR_ID": "S_APLT_TM_VAR", "APLT_TXT_MSG_ID": "S_APLT_TXT_MSG",
    "APPLET_ID": "S_APPLET", "APPLET_METH_MI_ID": "S_APPLET_METH_MI", "APPLICATION_ID": "S_APPLICATION",
    "APPL_METH_MI_ID": "S_APPL_METH_MI", "APPL_WEB_TMPL_ID": "S_APPL_WEB_TMPL", "APPL_WTMPL_IT_ID": "S_APPL_WTMPL_IT",
    "ASGN_ATTR_ID": "S_ASGN_ATTR", "ASGN_CNDT_ID": "S_ASGN_CNDT", "ASGN_DYN_COMP_ID": "S_ASGN_DYN_COMP",
    "ASGN_ITEM_ATTR_ID": "S_ASGN_ITEM_ATTR", "ASGN_ITEM_TYPE_ID": "S_ASGN_ITEM_TYPE", "ASGN_OBJECT_ID": "S_ASGN_OBJECT",
    "BITMAP_CAT_ID": "S_BITMAP_CAT", "BITMAP_ID": "S_BITMAP", "BRANCH_ID": "S_WFR_STP_BRNCH",
    "BUSCOMP_ID": "S_BUSCOMP", "BUSOBJ_ID": "S_BUSOBJ", "CHART_ELEM_ID": "S_CHART_ELEMENT", "CHART_ID": "S_CHART",
    "CLASS_ID": "S_CLASS", "CLASS_METH_MI_ID": "S_CLASS_METH_MI", "CLASS_UPROP_ID": "S_CLASS_UPROP",
    "COMMAND_ID": "S_COMMAND", "COMP_EVT_ID": "S_TU_EVT", "COND_CRIT_ID": "S_WFR_COND_CRIT",
    "CONTENT_OBJ_ID": "S_CONTENT_OBJ", "CONTROL_ID": "S_CONTROL", "DDOWN_OBJECT_ID": "S_DDOWN_OBJECT",
    "DIAGRAM_ID": "S_ER_DIAGRAM", "ENTITY_ID": "S_ER_ENTITY", "ENTITY_REL_ID": "S_ER_RELATION",
    "ERR_MSG_CAT_ID": "S_ERR_MSG_CAT", "ERR_MSG_ID": "S_ERR_MSG", "ESCL_OBJECT_ID": "S_ESCL_OBJECT",
    "ESCL_OBJ_ID": "S_ESCL_OBJECT", "FIELD_ID": "S_FIELD", "FIND_FLD_ID": "S_FIND_FIELD", "FIND_ID": "S_FIND",
    "ICON_MAP_ID": "S_ICON_MAP", "IMPORT_ID": "S_IMPORT_OBJECT", "IMP_FLD_ID": "S_IMPORT_FIELD",
    "IMP_SOURCE_ID": "S_IMPORT_SOURCE", "INT_COMP_ID": "S_INT_COMP", "INT_FIELD_ID": "S_INT_FIELD",
    "INT_KEY_ID": "S_INT_CKEY", "INT_OBJ_ID": "S_INT_OBJ", "JOIN_ID": "S_JOIN", "LIST_COLUMN_ID": "S_LIST_COLUMN",
    "LIST_ID": "S_LIST", "MENU_ID": "S_MENU", "MENU_ITEM_ID": "S_MENU_ITEM", "MODULE_ID": "S_MODULE",
    "PAGE_TAB_ID": "S_PAGE_TAB", "PROCESS_ID": "S_WFR_PROC", "PROGRAM_ID": "S_PROG_DEFN", "REPORT_ID": "S_REPORT",
    "SCREEN_ID": "S_SCREEN", "SCREEN_MENU_IT_ID": "S_SCR_MENU_ITEM", "SCREEN_VIEW_ID": "S_SCREEN_VIEW",
    "SERVICE_ID": "S_SERVICE", "SERVICE_METH_ID": "S_SERVICE_METH", "SERVICE_M_ARG_ID": "S_SERVICE_M_ARG",
    "SRCHENG_FLD_ID": "S_SRCHENG_FIELD", "SRCHENG_ID": "S_EXT_SRCH_ENG", "SRCHENG_TABLE_ID": "S_SRCHENG_TABLE",
    "SRCHENG_TBL_ID": "S_SRCHENG_TABLE", "SRCH_CAT_ID": "S_SRCH_CAT", "SRCH_CTRESFLD_ID": "S_SRCH_CTRESFLD",
    "SRCH_DEFCAT_ID": "S_SRCH_DEF_CAT", "SRCH_DEF_ID": "S_SRCH_DEF", "SRCH_ENG_ID": "S_SRCH_ENG",
    "SRCH_INDEX_ID": "S_SRCH_INDEX", "SRCH_TABLE_ID": "S_SRCH_TABLE", "STEP_ID": "S_WFR_STP",
    "STRING_MAP_ID": "S_STRING_MAP", "SYM_STR_ID": "S_SYM_STR", "TASK_BRANCH_ID": "S_TU_BRANCH",
    "TASK_BRNCH_COND_ID": "S_TU_BRNCH_COND", "TASK_CHAPTER_ID": "S_TU_CHAPTER", "TASK_GRP_ID": "S_TU_TASK_GRP",
    "TASK_ID": "S_TU_TASK", "TASK_STEP_ID": "S_TU_STEP", "TOOLBAR_ID": "S_TOOLBAR", "TOOLBAR_ITEM_ID": "S_TOOLBAR_ITEM",
    "TREE_ID": "S_TREE", "TREE_NODE_ID": "S_TREE_NODE", "VIEW_ID": "S_VIEW", "VIEW_REPORT_ID": "S_VIEW_REPORT",
    "VIEW_TG_ID": "S_VIEW_TG", "VIEW_WEB_TMPL_ID": "S_VIEW_WEB_TMPL", "VIEW_WTMPL_IT_ID": "S_VIEW_WTMPL_IT",
    "WEB_PAGE_ID": "S_WEB_PG", "WEB_PG_ID": "S_WEB_PG", "WEB_PG_ITM_ID": "S_WEB_PG_ITM", "WEB_TMPL_ID": "S_WEB_TMPL",
    "WEB_TMPL_IT_ID": "S_WEB_TMPL_IT",
}

# Tables whose parent cannot be told from the column name alone.
PARENT_BY_TABLE = {
    "S_ESCL_LINK": "S_ESCL_OBJECT", "S_WFR_PROC_FLOW": "S_WFR_STP_BRNCH",
    # extension (_RX) tables hang off the table they extend
    "S_APPLET_RX": "S_APPLET", "S_APPL_WTMPL_RX": "S_APPL_WEB_TMPL", "S_APPL_WT_IT_RX": "S_APPL_WTMPL_IT",
    "S_VIEW_RX": "S_VIEW", "S_VIEW_WT_IT_RX": "S_VIEW_WTMPL_IT", "S_WEB_PG_ITM_RX": "S_WEB_PG_ITM",
    "S_WEB_PG_RX": "S_WEB_PG", "S_WEB_TMPL_RX": "S_WEB_TMPL",
    # the S_P... family mirrors applets and views with the same column names
    "S_PAPL_BRSSCRPT": "S_PAPPLET", "S_PAPL_METH_MI": "S_PAPPLET", "S_PAPL_SCRIPT": "S_PAPPLET",
    "S_PAPL_TOGGLE": "S_PAPPLET", "S_PAPL_UPROP": "S_PAPPLET", "S_PAPL_WEBSCRPT": "S_PAPPLET",
    "S_PAPL_WEB_TMPL": "S_PAPPLET", "S_PAPPLET_INTL": "S_PAPPLET", "S_PCHART": "S_PAPPLET",
    "S_PCONTROL": "S_PAPPLET", "S_PDDWN_OBJECT": "S_PAPPLET", "S_PLIST": "S_PAPPLET", "S_PTREE": "S_PAPPLET",
    "S_PAPL_MMI_INTL": "S_PAPL_METH_MI", "S_PAPL_WTI_INTL": "S_PAPL_WTMPL_IT", "S_PAPL_WTMPL_IT": "S_PAPL_WEB_TMPL",
    "S_PCHART_EL": "S_PCHART", "S_PCHART_INTL": "S_PCHART", "S_PCHART_E_INTL": "S_PCHART_EL",
    "S_PCONTROL_INTL": "S_PCONTROL", "S_PCONTROL_UPRP": "S_PCONTROL", "S_PDDWN_DYNDEST": "S_PDDWN_OBJECT",
    "S_PDDWN_OB_INTL": "S_PDDWN_OBJECT", "S_PLISTCOL_INTL": "S_PLIST_COLUMN", "S_PLISTCOL_UPRP": "S_PLIST_COLUMN",
    "S_PLIST_COLUMN": "S_PLIST", "S_PLIST_INTL": "S_PLIST", "S_PTREE_NODE": "S_PTREE",
    "S_PTREE_ND_INTL": "S_PTREE_NODE", "S_PVIEW_INTL": "S_PVIEW", "S_PVIEW_REPORT": "S_PVIEW",
    "S_PVW_WEB_TMPL": "S_PVIEW", "S_PVW_RPT_INTL": "S_PVIEW_REPORT", "S_PVW_WTI_INTL": "S_PVW_WTMPL_IT",
    "S_PVW_WTMPL_IT": "S_PVW_WEB_TMPL",
}

# Tables with no <TABLE>_U1 index: (parent column, parent table).
NO_INDEX = {
    "S_BUSCOMP_SCRIPT": ("BUSCOMP_ID", "S_BUSCOMP"),
    "S_APPLET_METH_MI": ("APPLET_ID", "S_APPLET"),
}

# Siebel Tools names. A table missing here is shown by its table name.
LABELS = {
    "S_APPLET": "Applet", "S_APPLICATION": "Application", "S_BUSCOMP": "Business Component",
    "S_BUSOBJ": "Business Object", "S_CLASS": "Class", "S_COMMAND": "Command", "S_INT_OBJ": "Integration Object",
    "S_LINK": "Link", "S_MENU": "Menu", "S_PICKLIST": "Pick List", "S_SCREEN": "Screen",
    "S_SERVICE": "Business Service", "S_VIEW": "View", "S_WFR_PROC": "Workflow Process", "S_TU_TASK": "Task",
    "S_TU_TASK_GRP": "Task Group", "S_WEB_TMPL": "Web Template", "S_WEB_PG": "Web Page", "S_TOOLBAR": "Toolbar",
    "S_SYM_STR": "Symbolic String", "S_BITMAP_CAT": "Bitmap Category", "S_ICON_MAP": "Icon Map",
    "S_ERR_MSG_CAT": "Message Category", "S_FIND": "Find", "S_REPORT": "Report", "S_STRING_MAP": "String Map",
    "S_TEXT_STYLE": "Text Style", "S_HELP_ID": "Help Id", "S_DLL": "DLL", "S_ESCL_OBJECT": "Workflow Policy Object",
    "S_ESCL_COL": "Workflow Policy Column", "S_PROG_DEFN": "Workflow Policy Program",
    "S_ASGN_ATTR": "Assignment Attribute", "S_IMPORT_OBJECT": "Import Object", "S_CONTENT_OBJ": "Content Object",
    "S_ER_DIAGRAM": "Entity Relationship Diagram", "S_PAGER_OBJECT": "Pager Object",
    "S_SYSACT_OBJECT": "System Activity Object",
    "S_CONTROL": "Control", "S_CONTROL_UPROP": "Control User Prop", "S_LIST": "List", "S_LIST_COLUMN": "List Column",
    "S_LISTCOL_UPROP": "List Column User Prop", "S_APPLET_SCRIPT": "Applet Server Script",
    "S_APLT_BRSSCRPT": "Applet Browser Script", "S_APPLET_UPROP": "Applet User Prop",
    "S_APPL_WEB_TMPL": "Applet Web Template", "S_APPL_WTMPL_IT": "Applet Web Template Item",
    "S_APPLET_TOGGLE": "Applet Toggle", "S_APPLET_METH_MI": "Applet Method Menu Item",
    "S_DDOWN_OBJECT": "Drilldown Object", "S_DDOWN_DYNDEST": "Dynamic Drilldown Destination",
    "S_TREE": "Tree", "S_TREE_NODE": "Tree Node", "S_CHART": "Chart", "S_CHART_ELEMENT": "Chart Element",
    "S_FIELD": "Field", "S_FIELD_UPROP": "Field User Prop", "S_BUSCOMP_UPROP": "Business Component User Prop",
    "S_BUSCOMP_SCRIPT": "BusComp Server Script", "S_BC_BRS_SCRPT": "BusComp Browser Script",
    "S_BC_VIEWMODE": "BusComp View Mode", "S_JOIN": "Join", "S_JOIN_SPEC": "Join Specification",
    "S_JOIN_CONSTRNT": "Join Constraint", "S_MVLINK": "Multi Value Link", "S_PICKMAP": "Pick Map",
    "S_BOCOMP": "Business Object Component", "S_VIEW_WEB_TMPL": "View Web Template",
    "S_VIEW_WTMPL_IT": "View Web Template Item", "S_VIEW_UPROP": "View User Prop", "S_SCREEN_VIEW": "Screen View",
    "S_INT_COMP": "Integration Component", "S_INT_FIELD": "Integration Component Field",
    "S_INT_CKEY": "Integration Component Key", "S_INT_CKEY_FLD": "Integration Component Key Field",
    "S_INT_OBJ_UPROP": "Integration Object User Prop", "S_INTCOMP_UPROP": "Integration Component User Prop",
    "S_INTFLD_UPROP": "Integration Component Field User Prop", "S_SERVICE_METH": "Business Service Method",
    "S_SERVICE_M_ARG": "Business Service Method Arg", "S_SERVICE_SCRPT": "Business Service Server Script",
    "S_SVC_BRS_SCRPT": "Business Service Browser Script", "S_SERVICE_UPROP": "Business Service User Prop",
    "S_WFR_STP": "WF Step", "S_WFR_STP_ARG": "WF Step I/O Argument", "S_WFR_STP_BRNCH": "WF Step Branch",
    "S_WFR_PROC_PROP": "WF Process Prop", "S_WFR_COND_CRIT": "WF Branch Criteria",
    "S_WFR_COND_VAL": "WF Branch Criteria Value", "S_APPL_UPROP": "Application User Prop",
    "S_APPL_SCRIPT": "Application Server Script", "S_APPL_BRSSCRPT": "Application Browser Script",
    "S_PAGE_TAB": "Page Tab", "S_SCR_MENU_ITEM": "Screen Menu Item", "S_APPL_FIND": "Application Find",
    "S_APPL_TOOLBAR": "Application Toolbar", "S_MENU_ITEM": "Menu Item", "S_TOOLBAR_ITEM": "Toolbar Item",
    "S_CLASS_METHOD": "Class Method", "S_CLASS_UPROP": "Class User Prop", "S_SYM_STR_INTL": "Symbolic String Locale",
    "S_ERR_MSG": "Message", "S_BITMAP": "Bitmap", "S_ICON": "Icon", "S_WEB_TMPL_FILE": "Web Template File",
    "S_WEB_PG_ITM": "Web Page Item", "S_TU_STEP": "Task Step", "S_TU_BRANCH": "Task Branch",
}


def label(table):
    if table in LABELS:
        return LABELS[table]
    if table.endswith("_RX") and table in PARENT_BY_TABLE:
        return label(PARENT_BY_TABLE[table]) + " extension"
    if table.endswith("_INTL"):
        return table + " (locale)"
    return table


class Table:
    def __init__(self, name, parent_column=None, parent=None, has_name=True, known=True):
        self.name = name
        self.parent_column = parent_column
        self.parent = parent
        self.has_name = has_name
        self.known = known        # False: no usable index, so its place in the hierarchy is unknown
        self.label = label(name)

    @property
    def top_level(self):
        return self.known and self.parent_column is None


def describe(table_names, index_rows):
    """Build {table name: Table} from the table list and the (table, position, column) rows of the U1 indexes."""
    columns = {}
    for table, _position, column in index_rows:
        columns.setdefault(table, []).append(column)
    tables = {}
    for name in table_names:
        if not _IDENT.match(name):
            continue
        if name in columns:
            parent_column = next((c for c in columns[name] if c not in _NOT_PARENT), None)
            if parent_column and not _IDENT.match(parent_column):
                parent_column = None
            parent = PARENT_BY_TABLE.get(name) or PARENT_BY_COLUMN.get(parent_column)
            tables[name] = Table(name, parent_column, parent, "NAME" in columns[name])
        elif name in NO_INDEX:
            tables[name] = Table(name, *NO_INDEX[name])
        else:
            tables[name] = Table(name, known=False)
    return tables
