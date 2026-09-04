import 'package:flutter_test/flutter_test.dart';
import 'package:business_ai_robot/main.dart';
import 'package:business_ai_robot/widgets/stat_card.dart';
import 'package:business_ai_robot/widgets/robot_status_card.dart';
import 'package:business_ai_robot/widgets/quick_action_button.dart';

void main() {
  testWidgets('App renders dashboard with all primary sections and KPI cards', (WidgetTester tester) async {
    // Build the app
    await tester.pumpWidget(const BusinessAIRobotApp());
    await tester.pumpAndSettle();

    // Verify Dashboard title
    expect(find.text('Dashboard'), findsOneWidget);

    // Verify Robot Status Card
    expect(find.byType(RobotStatusCard), findsOneWidget);
    expect(find.text('Business AI Robot'), findsOneWidget);
    expect(find.text('Ready'), findsOneWidget);

    // Verify Overview Section and KPI StatCards
    expect(find.text("Today's Overview"), findsOneWidget);
    expect(find.byType(StatCard), findsNWidgets(4));
    expect(find.text('Sales'), findsOneWidget);
    expect(find.text('₹18,450'), findsOneWidget);
    expect(find.text('Orders'), findsOneWidget);
    expect(find.text('47'), findsOneWidget);
    expect(find.text('Pending'), findsOneWidget);
    expect(find.text('₹3,200'), findsOneWidget);
    expect(find.text('Low Stock'), findsOneWidget);
    expect(find.text('3'), findsOneWidget);

    // Verify Quick Actions Section and 4 Action Buttons
    expect(find.text('Quick Actions'), findsOneWidget);
    expect(find.byType(QuickActionButton), findsNWidgets(4));
    expect(find.text('New Bill'), findsOneWidget);
    expect(find.text('Add Stock'), findsOneWidget);
    expect(find.text('Voice Cmd'), findsOneWidget);
    expect(find.text('Reminders'), findsOneWidget);

    // Verify Bottom Navigation Items
    expect(find.text('Home'), findsOneWidget);
    expect(find.text('Robot'), findsOneWidget);
    expect(find.text('Reports'), findsOneWidget);
    expect(find.text('More'), findsOneWidget);
  });

  testWidgets('Navigation bar switches to Robot tab', (WidgetTester tester) async {
    await tester.pumpWidget(const BusinessAIRobotApp());
    await tester.pumpAndSettle();

    // Tap on Robot tab
    await tester.tap(find.text('Robot'));
    await tester.pumpAndSettle();

    // Verify Robot Assistant screen is displayed
    expect(find.text('Tap to speak'), findsOneWidget);
    expect(find.text('Stop'), findsOneWidget);
  });

  testWidgets('Navigation bar switches to Reports tab', (WidgetTester tester) async {
    await tester.pumpWidget(const BusinessAIRobotApp());
    await tester.pumpAndSettle();

    // Tap on Reports tab
    await tester.tap(find.text('Reports'));
    await tester.pumpAndSettle();

    // Verify Reports screen is displayed
    expect(find.text('Reports & Analytics'), findsOneWidget);
    expect(find.text('AI Summary'), findsOneWidget);
  });

  testWidgets('Navigation bar switches to More (Settings) tab', (WidgetTester tester) async {
    await tester.pumpWidget(const BusinessAIRobotApp());
    await tester.pumpAndSettle();

    // Tap on More tab
    await tester.tap(find.text('More'));
    await tester.pumpAndSettle();

    // Verify Settings screen is displayed
    expect(find.text('Settings'), findsOneWidget);
    expect(find.text('ACCOUNT'), findsOneWidget);
    expect(find.text('BUSINESS'), findsOneWidget);
  });
}
