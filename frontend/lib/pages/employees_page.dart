import 'package:flutter/material.dart';
import 'package:avenqo/core/api_client.dart';
import 'package:avenqo/i18n/locale_scope.dart';

class EmployeesPage extends StatefulWidget {
  const EmployeesPage({super.key, required this.api});
  final ApiClient api;

  @override
  State<EmployeesPage> createState() => _EmployeesPageState();
}

class _EmployeesPageState extends State<EmployeesPage> {
  late Future<dynamic> _employees = widget.api.get('/employees');

  @override
  Widget build(BuildContext context) {
    final t = AvenqoLocaleScope.translationsOf(context).company;
    return FutureBuilder<dynamic>(
      future: _employees,
      builder: (context, snapshot) {
        final users = snapshot.data is List
            ? snapshot.data as List<dynamic>
            : const <dynamic>[];
        return ListView(
          padding: const EdgeInsets.all(24),
          children: [
            Row(
              children: [
                Expanded(
                  child: Text(
                    t.employeesTitle,
                    style: Theme.of(context).textTheme.headlineMedium,
                  ),
                ),
                IconButton(
                  tooltip: t.employeesRefreshTooltip,
                  onPressed: () =>
                      setState(() => _employees = widget.api.get('/employees')),
                  icon: const Icon(Icons.refresh),
                ),
              ],
            ),
            const SizedBox(height: 20),
            if (snapshot.connectionState != ConnectionState.done)
              const Center(child: CircularProgressIndicator())
            else if (snapshot.hasError)
              Card(
                child: Padding(
                  padding: const EdgeInsets.all(20),
                  child: Text(t.employeesUnavailable),
                ),
              )
            else
              Card(
                child: DataTable(
                  columns: [
                    DataColumn(label: Text(t.employeesColumnName)),
                    DataColumn(label: Text(t.employeesColumnEmail)),
                    DataColumn(label: Text(t.employeesColumnRole)),
                    DataColumn(label: Text(t.employeesColumnStatus)),
                  ],
                  rows: [
                    for (final user in users)
                      DataRow(
                        cells: [
                          DataCell(
                            Text('${user['first_name']} ${user['last_name']}'),
                          ),
                          DataCell(Text(user['email'].toString())),
                          DataCell(Text(user['role'].toString())),
                          DataCell(
                            Icon(
                              user['is_active'] == true
                                  ? Icons.check_circle
                                  : Icons.cancel_outlined,
                            ),
                          ),
                        ],
                      ),
                  ],
                ),
              ),
          ],
        );
      },
    );
  }
}
