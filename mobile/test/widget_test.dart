import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:omnifind_mobile/main.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  testWidgets('Image evidence is labeled OCR and asks users to verify the original', (tester) async {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(const MethodChannel('omnifind/phone'), (call) async {
      if (call.method == 'search') return [{'uri': 'synthetic-image', 'name': 'receipt.png', 'sha': 'fixture', 'kind': 'ocr', 'line': 2, 'text': 'Reference PKG-483', 'score': 1.0}];
      return [];
    });
    await tester.pumpWidget(const OmniFindApp());
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField), 'PKG-483');
    await tester.tap(find.widgetWithText(FilledButton, 'Search'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('receipt.png'));
    await tester.pumpAndSettle();
    expect(find.text('Recognized image text · OCR line 2'), findsOneWidget);
    expect(find.text('OCR can misread words and codes. Open the original image to verify this passage.'), findsOneWidget);
    expect(find.text('Open original'), findsOneWidget);
  });
  testWidgets('In-flight search locks the query; changing mode clears old evidence', (tester) async {
    final pending = Completer<List<Map<String, dynamic>>>();
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(const MethodChannel('omnifind/phone'), (call) async {
      if (call.method == 'search') return pending.future;
      return [];
    });
    await tester.pumpWidget(const OmniFindApp());
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField), 'rental deposit');
    await tester.tap(find.widgetWithText(FilledButton, 'Search'));
    await tester.pump();
    expect(tester.widget<TextField>(find.byType(TextField)).enabled, isFalse);
    pending.complete([{'uri': 'synthetic-file', 'name': 'agreement.pdf', 'sha': 'fixture', 'page': 2, 'line': 1, 'text': 'Rental deposit returned', 'score': 1.0}]);
    await tester.pumpAndSettle();
    expect(tester.widget<TextField>(find.byType(TextField)).enabled, isTrue);
    await tester.tap(find.text('agreement.pdf'));
    await tester.pumpAndSettle();
    expect(find.text('Original source · Page 2 · extracted line 1'), findsOneWidget);
    await tester.pageBack();
    await tester.pumpAndSettle();
    await tester.tap(find.byType(SwitchListTile));
    await tester.pumpAndSettle();
    expect(find.text('agreement.pdf'), findsNothing);
    expect(find.text('rental deposit'), findsOneWidget);
  });
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
