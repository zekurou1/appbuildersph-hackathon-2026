import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:omnifind_mobile/main.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  testWidgets('Folder removal clears evidence and preserves the query', (tester) async {
    const channel = MethodChannel('omnifind/phone');
    var removed = false;
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(channel, (call) async => switch (call.method) {
      'roots' => removed ? [] : [{'uri': 'synthetic-root', 'name': 'Demo', 'available': true, 'files': 1, 'issues': 0}],
      'search' => [{'uri': 'synthetic-file', 'name': 'receipt.txt', 'sha': 'fixture', 'line': 1, 'text': 'Receipt PKG-483', 'score': 1.0}],
      'remove' => removed = true,
      _ => null,
    });
    await tester.pumpWidget(const OmniFindApp());
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField), 'PKG-483');
    await tester.tap(find.widgetWithText(FilledButton, 'Search'));
    await tester.pumpAndSettle();
    expect(find.text('receipt.txt'), findsOneWidget);
    await tester.tap(find.text('Folders'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Remove'));
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(FilledButton, 'Remove'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Search').last);
    await tester.pumpAndSettle();
    expect(find.text('receipt.txt'), findsNothing);
    expect(find.text('PKG-483'), findsOneWidget);
  });
  testWidgets('Stale Open clears the detail and preserves the query', (tester) async {
    const channel = MethodChannel('omnifind/phone');
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(channel, (call) async {
      if (call.method == 'roots') { return []; }
      if (call.method == 'search') { return [{'uri': 'synthetic-file', 'name': 'receipt.txt', 'sha': 'fixture', 'line': 1, 'text': 'Old receipt passage', 'score': 1.0}]; }
      if (call.method == 'open') { throw PlatformException(code: 'source-changed'); }
      return null;
    });
    await tester.pumpWidget(const OmniFindApp());
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField), 'PKG-483');
    await tester.tap(find.widgetWithText(FilledButton, 'Search'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('receipt.txt'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Open original'));
    await tester.pumpAndSettle();
    expect(find.text('Old receipt passage'), findsNothing);
    expect(find.text('This file changed. Refresh the folder before opening it.'), findsOneWidget);
    expect(find.text('PKG-483'), findsOneWidget);
  });
  testWidgets('Phone layout remains usable with doubled text', (tester) async {
    await tester.binding.setSurfaceSize(const Size(390, 844));
    tester.platformDispatcher.textScaleFactorTestValue = 2;
    addTearDown(() async {
      tester.platformDispatcher.clearTextScaleFactorTestValue();
      await tester.binding.setSurfaceSize(null);
    });
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(const MethodChannel('omnifind/phone'), (_) async => []);
    await tester.pumpWidget(const OmniFindApp());
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);
    await tester.tap(find.byIcon(Icons.folder_outlined));
    await tester.pumpAndSettle();
    expect(find.text('Selected folders'), findsOneWidget);
    await tester.scrollUntilVisible(find.text('Choose folder'), 150, scrollable: find.byType(Scrollable).first);
    expect(find.text('Choose folder'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
}
