import 'package:data_table_2/data_table_2.dart';
import 'package:flutter/material.dart';

class AvenqoDataTable extends StatelessWidget {
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
  Widget build(BuildContext context) {
    final contentHeight = 56.0 + rows.length * 56.0;
    final height = contentHeight.clamp(112.0, maxHeight).toDouble();
    return Semantics(
      container: true,
      label: semanticLabel,
      child: SizedBox(
        height: height,
        child: DataTable2(
          minWidth: minWidth,
          fixedTopRows: 1,
          fixedLeftColumns: fixedLeftColumns,
          isHorizontalScrollBarVisible: true,
          isVerticalScrollBarVisible: contentHeight > maxHeight,
          columnSpacing: 24,
          horizontalMargin: 16,
          headingTextStyle: headingTextStyle,
          dataTextStyle: dataTextStyle,
          columns: columns,
          rows: rows,
        ),
      ),
    );
  }
}