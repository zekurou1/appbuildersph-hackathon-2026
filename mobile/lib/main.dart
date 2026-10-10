import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

void main() => runApp(const OmniFindApp());

class OmniFindApp extends StatelessWidget {
  const OmniFindApp({super.key});
  @override
  Widget build(BuildContext context) => MaterialApp(
    title: 'OmniFind Local',
    theme: ThemeData(colorSchemeSeed: const Color(0xff286454), useMaterial3: true),
    darkTheme: ThemeData(colorSchemeSeed: const Color(0xff286454), brightness: Brightness.dark, useMaterial3: true),
    home: const PhoneSearch(),
  );
}

class PhoneSearch extends StatefulWidget {
  const PhoneSearch({super.key});
  @override
  State<PhoneSearch> createState() => _PhoneSearchState();
}

class _PhoneSearchState extends State<PhoneSearch> with WidgetsBindingObserver {
  static const bridge = MethodChannel('omnifind/phone');
  final query = TextEditingController();
  List<Map<String, dynamic>> roots = [], results = [];
  int destination = 0;
  bool busy = false, wordsOnly = false;
  String status = 'Choose a phone folder to begin.';
  @override
  void initState() { super.initState(); WidgetsBinding.instance.addObserver(this); loadRoots(); }
  @override
  void dispose() { WidgetsBinding.instance.removeObserver(this); query.dispose(); super.dispose(); }
  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed && mounted) {
      Navigator.of(context).popUntil((route) => route.isFirst);
      setState(() {
        if (results.isNotEmpty) { status = 'Submit Search again to check current files.'; }
        results = [];
      });
      loadRoots();
    }
    if (state == AppLifecycleState.paused && busy) bridge.invokeMethod<void>('cancel');
  }
  Future<void> loadRoots() async {
    try {
      final value = await bridge.invokeListMethod<dynamic>('roots');
      if (mounted) {
        setState(() {
          roots = (value ?? []).map((r) => Map<String, dynamic>.from(r as Map)).toList();
          if (roots.isNotEmpty && status == 'Choose a phone folder to begin.') {
            status = 'Search selected phone folders. Refresh to prepare new or changed files.';
          }
        });
      }
    } on PlatformException {
      if (mounted) setState(() => status = 'Folder access is unavailable. Choose the folder again.');
    }
  }
  String problem(PlatformException e) => switch (e.code) {
    'choose-local-storage' => 'Choose a folder on this phone. Cloud providers are not supported.',
    'indexing-cancelled' => 'Canceled. Indexed files are kept. Refresh to continue.',
    'query-too-long' => 'Try a shorter description.',
    'query-needs-words' => 'Enter a word or file code to search.',
    'file-count-limit' => 'This folder exceeds the 200-file pilot limit. Choose a smaller folder.',
    'source-changed' => 'This file changed. Refresh the folder before opening it.',
    'open-unavailable' => 'No viewer is available for this file.',
    _ => 'The operation could not finish. Refresh the folder or choose it again.',
  };
  Future<void> work(Future<void> Function() action) async {
    if (busy) return;
    setState(() => busy = true);
    try { await action(); }
    on PlatformException catch (e) { if (mounted) setState(() => status = problem(e)); }
    finally { if (mounted) setState(() => busy = false); }
  }
  Future<void> pick() => work(() async {
    final selected = await bridge.invokeMethod<String>('pick');
    await loadRoots();
    if (mounted && selected != null) setState(() => status = 'Folder added. Refresh it to prepare search.');
  });
  Future<void> refresh(Map<String, dynamic> root) => work(() async {
    setState(() { results = []; status = 'Preparing local search…'; });
    final coverage = await bridge.invokeMapMethod<String, dynamic>('refresh', {'root': root['uri']});
    await loadRoots();
    if (mounted) setState(() => status = '${coverage?['searchable']} searchable files; ${coverage?['issues']} files could not be indexed.');
  });
  Future<void> search() => work(() async {
    FocusScope.of(context).unfocus();
    setState(() { results = []; status = 'Searching on this phone…'; });
    final value = await bridge.invokeListMethod<dynamic>('search', {'query': query.text.trim(), 'wordsOnly': wordsOnly});
    if (mounted) {
      setState(() {
      results = (value ?? []).map((r) => Map<String, dynamic>.from(r as Map)).toList();
      status = results.isEmpty ? 'No strong match. Try another description, Words only, or refresh.' : '${results.length} matching ${results.length == 1 ? 'file' : 'files'}';
      });
    }
  });
  Future<void> remove(Map<String, dynamic> root) async {
    final confirmed = await showDialog<bool>(context: context, builder: (context) => AlertDialog(
      title: const Text('Remove folder?'), content: Text('Remove search text and vectors for ${root['name']}. Original files will be kept.'),
      actions: [TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Keep folder')),
        FilledButton(onPressed: () => Navigator.pop(context, true), child: const Text('Remove'))],
    ));
    if (confirmed != true) { return; }
    await work(() async {
      setState(() => results = []);
      await bridge.invokeMethod<void>('remove', {'root': root['uri']});
      await loadRoots();
      if (mounted) setState(() => status = 'Removed from search. Original files were kept.');
    });
  }
  Future<void> detail(Map<String, dynamic> result) async {
    await Navigator.push<void>(context, MaterialPageRoute(builder: (context) => Scaffold(
      appBar: AppBar(title: Text(result['name'] as String)),
      body: ListView(padding: const EdgeInsets.all(24), children: [
        Text('Original source · line ${result['line']}', style: Theme.of(context).textTheme.labelLarge),
        const SizedBox(height: 16), SelectableText(result['text'] as String, style: Theme.of(context).textTheme.bodyLarge),
        const SizedBox(height: 24), const Text('An excerpt from your file. Search does not generate an answer.'),
      ]),
      bottomNavigationBar: SafeArea(child: Padding(padding: const EdgeInsets.all(16), child: FilledButton.icon(
        icon: const Icon(Icons.open_in_new), label: const Text('Open original'), onPressed: () async {
          try { await bridge.invokeMethod<void>('open', {'uri': result['uri'], 'sha': result['sha']}); }
          on PlatformException catch (e) {
            if (!context.mounted) { return; }
            if (e.code == 'source-changed' || e.code == 'source-unavailable' || e.code == 'folder-unavailable') {
              Navigator.of(context).popUntil((route) => route.isFirst);
              if (mounted) { setState(() { results = []; status = problem(e); }); }
            } else {
              ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(problem(e))));
            }
          }
        },
      ))),
    )));
  }
  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(title: const Text('OmniFind Local')),
    body: SafeArea(child: Column(children: [
      if (busy) const LinearProgressIndicator(semanticsLabel: 'Local operation in progress'),
      Expanded(child: switch (destination) {
        0 => ListView(padding: const EdgeInsets.all(20), children: [
          Text('Find a phone file', style: Theme.of(context).textTheme.headlineMedium),
          const SizedBox(height: 8), const Text('Describe what you remember. Only selected phone folders are searched.'),
          const SizedBox(height: 20), TextField(controller: query, maxLength: 1000, minLines: 1, maxLines: 4,
            onChanged: (_) => setState(() { results = []; status = 'Submit Search to find current files.'; }),
            decoration: InputDecoration(labelText: 'Find a file', hintText: 'When is my rental deposit returned?', border: const OutlineInputBorder(),
              suffixIcon: IconButton(tooltip: 'Clear query', icon: const Icon(Icons.close), onPressed: busy ? null : () {
                query.clear(); setState(() { results = []; status = 'Enter what you remember, then Search.'; });
              })),
            textInputAction: TextInputAction.search, onSubmitted: (_) { if (!busy) search(); }),
          SwitchListTile(contentPadding: EdgeInsets.zero, title: const Text('Words only'),
            subtitle: Text(wordsOnly ? 'Literal source words and codes' : 'Meaning + words · on this phone'),
            value: wordsOnly, onChanged: busy ? null : (value) => setState(() => wordsOnly = value)),
          FilledButton.icon(onPressed: busy ? null : search, icon: const Icon(Icons.search), label: const Text('Search')),
          const SizedBox(height: 16), Text(status),
          if (roots.isEmpty) Padding(padding: const EdgeInsets.only(top: 16), child: OutlinedButton(onPressed: busy ? null : pick, child: const Text('Choose phone folder'))),
          for (final result in results) Card(child: ListTile(title: Text(result['name'] as String),
            subtitle: Text('Line ${result['line']} · ${result['text']}'), trailing: const Icon(Icons.chevron_right), onTap: busy ? null : () => detail(result))),
        ]),
        1 => ListView(padding: const EdgeInsets.all(20), children: [
          Text('Selected folders', style: Theme.of(context).textTheme.headlineMedium),
          const SizedBox(height: 12), const Text('Choose a subfolder on this phone. Text and Markdown are supported. PDF and screenshot OCR are unavailable in this mobile tier.'),
          const SizedBox(height: 12), FilledButton.icon(onPressed: busy ? null : pick, icon: const Icon(Icons.create_new_folder_outlined), label: const Text('Choose folder')),
          const SizedBox(height: 12), Text(status),
          for (final root in roots) Card(child: Padding(padding: const EdgeInsets.all(16), child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(root['name'] as String, style: Theme.of(context).textTheme.titleMedium),
            Text(root['available'] == true ? '${root['files']} files · ${root['issues']} issues' : 'Folder access unavailable. Choose it again.'),
            Wrap(spacing: 12, children: [TextButton.icon(onPressed: busy ? null : () => refresh(root), icon: const Icon(Icons.refresh), label: const Text('Refresh')),
              TextButton.icon(onPressed: busy ? null : () => remove(root), icon: const Icon(Icons.remove_circle_outline), label: const Text('Remove'))]),
          ]))),
        ]),
        _ => ListView(padding: const EdgeInsets.all(24), children: [
          Text('On this phone', style: Theme.of(context).textTheme.headlineMedium),
          const SizedBox(height: 16), const Text('Meaning search uses bundled MiniLM on the phone CPU. No cloud fallback, desktop connection or account.'),
          const SizedBox(height: 16), const Text('The local index contains readable source excerpts and vectors in app-private storage. Android backup is disabled. Query history is not saved. Originals stay in their folders.'),
          const SizedBox(height: 16), const Text('Pilot limits: English text and Markdown; 200 files per folder; 1 MiB per file; 20 MiB per refresh. Manual refresh is required after changes. Providers and external viewers have their own behavior.'),
          const SizedBox(height: 16), const Text('Experimental match threshold. Quality and performance need independent phone testing.'),
        ]),
      }),
      if (busy) TextButton(onPressed: () => bridge.invokeMethod<void>('cancel'), child: const Text('Cancel operation')),
    ])),
    bottomNavigationBar: NavigationBar(selectedIndex: destination, onDestinationSelected: (value) => setState(() => destination = value), destinations: const [
      NavigationDestination(icon: Icon(Icons.search), label: 'Search'), NavigationDestination(icon: Icon(Icons.folder_outlined), label: 'Folders'),
      NavigationDestination(icon: Icon(Icons.settings_outlined), label: 'Settings'),
    ]),
  );
}
