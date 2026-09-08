import 'package:data_table_2/data_table_2.dart';
import 'package:flutter/material.dart';

class AvenqoDataTable extends StatefulWidget {
  const AvenqoDataTable({
    super.key,
    required this.columns,
    required this.rows,
    required this.semanticLabel,
    this.minWidth = 900,
    this.maxHeight = 480,
    this.fixedLeftColumns = 1,
    this.headingTextStyle,
    this.dataTextStyle,
  });

  final List<DataColumn> columns;
  final List<DataRow> rows;
  final String semanticLabel;
  final double minWidth;
  final double maxHeight;
  final int fixedLeftColumns;
  final TextStyle? headingTextStyle;
  final TextStyle? dataTextStyle;

  @override
  State<AvenqoDataTable> createState() => _AvenqoDataTableState();
}

class _AvenqoDataTableState extends State<AvenqoDataTable> {
  final ScrollController _horizontalController = ScrollController();
  final ScrollController _verticalController = ScrollController();

  @override
  void dispose() {
    _horizontalController.dispose();
    _verticalController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final contentHeight = 56.0 + widget.rows.length * 56.0;
    final height = contentHeight.clamp(112.0, widget.maxHeight).toDouble();
    return Semantics(
      container: true,
      label: widget.semanticLabel,
      child: SizedBox(
        height: height,
        child: DataTable2(
          minWidth: widget.minWidth,
          fixedTopRows: 1,
          fixedLeftColumns: widget.fixedLeftColumns,
          isHorizontalScrollBarVisible: true,
          isVerticalScrollBarVisible: contentHeight > widget.maxHeight,
          horizontalScrollController: _horizontalController,
          scrollController: _verticalController,
          columnSpacing: 24,
          horizontalMargin: 16,
          headingTextStyle: widget.headingTextStyle,
          dataTextStyle: widget.dataTextStyle,
          columns: widget.columns,
          rows: widget.rows,
        ),
      ),
    );
  }
}