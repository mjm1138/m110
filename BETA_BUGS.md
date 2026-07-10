BETA_BUGS

- [x] Processing view: Replace the “Up to date” table with a table of objects with  processed files ready for import
- [x] Processing view: Table with a single row gets that row truncated. (Maybe leave a half-row of padding)
- [x] Processing view: Remove “Star removal” column. If we decide to give prescriptive advice about processing we can do it in the “Note” column, which should be renamed “Notes”
- [x] Overview view: dead space under the two active rows. Tables should scale appropriately when there are only 1-2 rows (maybe leave a half-row of padding)
- [x] Overview view: Order of collapsible sections
	1. Goals
	2. Priority targets
	3. Current Integrations
	4. Goal checklists
	5. Progress by category
	6. Manage Goals
- [x] Overview view: retire Processing queue table. It is redundant to the Processing Pane
- [x] Overview/Manage Goals view: since this is the only section that isn’t a table, lets draw a bounding box around it so the borders of the section are clear
- [x] Overview/Current Integrations view: Rename to Integration Time and Sessions and add a “Last 5 Sessions” table
- [x] Library: “List”, “Grid”, and “Feed” buttons relocate in Feed view. They should stay in one place and be styled as a single control similar to the Format, Animate, Document buttons in the upper-right corner of Apple Keynote’s main window (ask for samples if you need them). Do a similar treatment with the “Deep Sky” and “Media” buttons. Put the  “Deep Sky” and “Media” buttons justified left on the same row as “List”, “Grid”, and “Feed” justified right.
- [x] Priority Targets: Need to insert language about it being an in-development feature, and not populate the table with old data
- [x] Object Detail View: pad the Processing and Sessions tables so a whole row will fit, and allow them to vertically scale to accommodate 6 rows if >= 6 rows are present.
