package ph.appbuilders.omnifind_mobile

import android.content.ContentValues
import android.content.Context
import android.database.sqlite.SQLiteDatabase
import android.database.sqlite.SQLiteOpenHelper
import android.net.Uri
import android.provider.DocumentsContract as DC
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.security.MessageDigest
import java.util.concurrent.atomic.AtomicBoolean

/** Persist only explicitly selected local-provider content in app-private SQLite. */
class PhoneIndex(private val context: Context) : AutoCloseable {
    companion object {
        fun digest(bytes: ByteArray) = MessageDigest.getInstance("SHA-256").digest(bytes)
            .joinToString("") { "%02x".format(it.toInt() and 255) }
    }
    private val resolver = context.contentResolver
    private val extractor = PhoneTextExtractor(context)
    private val helper = object : SQLiteOpenHelper(context, "phone-index.sqlite", null, 2) {
        override fun onCreate(db: SQLiteDatabase) {
            db.execSQL("CREATE TABLE roots(uri TEXT PRIMARY KEY,name TEXT NOT NULL)")
            db.execSQL("CREATE TABLE files(uri TEXT PRIMARY KEY,root TEXT NOT NULL,name TEXT NOT NULL,sha TEXT NOT NULL,issue TEXT)")
            db.execSQL("CREATE TABLE chunks(uri TEXT NOT NULL,line INTEGER NOT NULL,text TEXT NOT NULL,vector BLOB NOT NULL,page INTEGER)")
            db.execSQL("CREATE INDEX chunks_uri ON chunks(uri)")
        }
        override fun onUpgrade(db: SQLiteDatabase, old: Int, new: Int) {
            if (old < 2) db.execSQL("ALTER TABLE chunks ADD COLUMN page INTEGER")
        }
    }
    private val db = helper.writableDatabase.apply { rawQuery("PRAGMA secure_delete=ON", null).use { it.moveToFirst() } }
    private var model: PhoneEmbedder? = null
    private fun embedder() = model ?: PhoneEmbedder(context).also { model = it }
    private fun values(vararg pairs: Pair<String, Any?>) = ContentValues().apply {
        for ((key, value) in pairs) when (value) {
            is String -> put(key, value)
            is Int -> put(key, value)
            is ByteArray -> put(key, value)
            null -> putNull(key)
        }
    }
    private fun allowed(root: String): Boolean = Uri.parse(root).authority == "com.android.externalstorage.documents" &&
        resolver.persistedUriPermissions.any { it.uri.toString() == root && it.isReadPermission } &&
        db.rawQuery("SELECT 1 FROM roots WHERE uri=?", arrayOf(root)).use { it.moveToFirst() }
    fun add(uri: Uri) {
        require(uri.authority == "com.android.externalstorage.documents") { "choose-local-storage" }
        val name = DC.getTreeDocumentId(uri).substringAfter(':').ifEmpty { "Selected folder" }
        db.insertWithOnConflict("roots", null, values("uri" to uri.toString(), "name" to name), SQLiteDatabase.CONFLICT_IGNORE)
    }
    fun roots(): List<Map<String, Any?>> = db.rawQuery("SELECT uri,name FROM roots ORDER BY name", null).use { cursor ->
        buildList {
            while (cursor.moveToNext()) {
                val uri = cursor.getString(0)
                val count = db.rawQuery("SELECT COUNT(*),SUM(CASE WHEN issue IS NOT NULL THEN 1 ELSE 0 END) FROM files WHERE root=?", arrayOf(uri)).use {
                    it.moveToFirst(); listOf(it.getInt(0), it.getInt(1))
                }
                val reasons = db.rawQuery("SELECT issue,COUNT(*) FROM files WHERE root=? AND issue IS NOT NULL GROUP BY issue", arrayOf(uri)).use {
                    buildMap<String, Int> { while (it.moveToNext()) put(it.getString(0), it.getInt(1)) }
                }
                add(mapOf("uri" to uri, "name" to cursor.getString(1), "available" to allowed(uri), "files" to count[0], "issues" to count[1], "issueReasons" to reasons))
            }
        }
    }
    private fun read(uri: Uri): ByteArray = resolver.openInputStream(uri)?.use {
        val output = java.io.ByteArrayOutputStream()
        val buffer = ByteArray(8192)
        while (output.size() <= 1_048_576) {
            val count = it.read(buffer, 0, minOf(buffer.size, 1_048_577 - output.size()))
            if (count < 0) break
            output.write(buffer, 0, count)
        }
        val bytes = output.toByteArray()
        require(bytes.size <= 1_048_576) { "file-too-large" }
        bytes
    } ?: error("source-unavailable")
    fun refresh(root: String, cancelled: AtomicBoolean): Map<String, Int> {
        require(allowed(root)) { "folder-unavailable" }
        val tree = Uri.parse(root)
        val seen = mutableSetOf<String>()
        var searchable = 0
        var issues = 0
        var totalBytes = 0
        fun checkpoint() { check(!cancelled.get()) { "indexing-cancelled" }; check(allowed(root)) { "folder-unavailable" } }
        fun visit(id: String, depth: Int) {
            require(depth <= 12) { "folder-depth-limit" }
            checkpoint()
            val children = DC.buildChildDocumentsUriUsingTree(tree, id)
            resolver.query(children, arrayOf(DC.Document.COLUMN_DOCUMENT_ID, DC.Document.COLUMN_DISPLAY_NAME, DC.Document.COLUMN_MIME_TYPE), null, null, null)?.use { cursor ->
                while (cursor.moveToNext()) {
                    checkpoint()
                    val child = cursor.getString(0)
                    val name = cursor.getString(1)
                    if (cursor.getString(2) == DC.Document.MIME_TYPE_DIR) { visit(child, depth + 1); continue }
                    require(seen.size < 200) { "file-count-limit" }
                    val uri = DC.buildDocumentUriUsingTree(tree, child)
                    seen.add(uri.toString())
                    var sha = ""
                    var issue: String? = null
                    val passages = mutableListOf<Pair<SourceLine, FloatArray>>()
                    try {
                        require(name.substringAfterLast('.').lowercase() in setOf("txt", "md", "pdf")) { "unsupported-type" }
                        val bytes = read(uri)
                        require(totalBytes + bytes.size <= 20 * 1_048_576) { "folder-size-limit" }
                        totalBytes += bytes.size
                        sha = digest(bytes)
                        for (source in extractor.extract(name, bytes, ::checkpoint)) {
                            val line = source.text
                            var offset = 0
                            while (offset < line.length) {
                                checkpoint()
                                require(passages.size < 2000) { "passage-count-limit" }
                                val slice = line.substring(offset, minOf(offset + 300, line.length))
                                if (slice.isNotBlank()) passages.add(source.copy(text = slice) to embedder().embed(slice))
                                offset += 240
                            }
                        }
                        require(passages.isNotEmpty()) { "no-searchable-text" }
                        require(digest(read(uri)) == sha) { "source-changed" }
                    } catch (error: Exception) {
                        checkpoint()
                        issue = if (error.message in setOf("unsupported-type", "file-too-large", "folder-size-limit", "source-changed", "passage-count-limit", "pdf-needs-android-15", "pdf-page-limit", "pdf-text-limit", "pdf-no-text", "pdf-unreadable", "no-searchable-text")) error.message else "file-could-not-be-indexed"
                        passages.clear()
                    }
                    checkpoint()
                    db.beginTransaction()
                    try {
                        db.delete("chunks", "uri=?", arrayOf(uri.toString()))
                        db.insertWithOnConflict("files", null, values("uri" to uri.toString(), "root" to root, "name" to name, "sha" to sha, "issue" to issue), SQLiteDatabase.CONFLICT_REPLACE)
                        for ((source, vector) in passages) {
                            val blob = ByteBuffer.allocate(384 * 4).order(ByteOrder.LITTLE_ENDIAN)
                            vector.forEach { blob.putFloat(it) }
                            db.insertOrThrow("chunks", null, values("uri" to uri.toString(), "line" to source.line, "page" to source.page, "text" to source.text, "vector" to blob.array()))
                        }
                        db.setTransactionSuccessful()
                    } finally { db.endTransaction() }
                    if (issue == null && passages.isNotEmpty()) searchable++ else issues++
                }
            } ?: error("folder-unavailable")
        }
        visit(DC.getTreeDocumentId(tree), 0)
        checkpoint()
        val obsolete = db.rawQuery("SELECT uri FROM files WHERE root=?", arrayOf(root)).use { cursor ->
            buildList { while (cursor.moveToNext()) if (cursor.getString(0) !in seen) add(cursor.getString(0)) }
        }
        for (uri in obsolete) { db.delete("chunks", "uri=?", arrayOf(uri)); db.delete("files", "uri=?", arrayOf(uri)) }
        return mapOf("searchable" to searchable, "issues" to issues)
    }
    fun search(query: String, wordsOnly: Boolean, cancelled: AtomicBoolean): List<Map<String, Any?>> {
        require(query.isNotBlank() && query.length <= 1000) { "query-too-long" }
        val words = Regex("[\\p{L}\\p{N}]+(?:[-_][\\p{L}\\p{N}]+)*").findAll(query.lowercase()).map { it.value }.toList()
        require(words.isNotEmpty()) { "query-needs-words" }
        val exact = words.size == 1 && words[0].any { it.isDigit() }
        val q = if (!wordsOnly && !exact) embedder().embed(query) else null
        check(!cancelled.get()) { "indexing-cancelled" }
        val matches = mutableMapOf<String, Map<String, Any?>>()
        val fresh = mutableMapOf<String, Boolean>()
        db.rawQuery("SELECT f.uri,f.root,f.name,f.sha,c.line,c.text,c.vector,c.page FROM chunks c JOIN files f ON f.uri=c.uri WHERE f.issue IS NULL", null).use { cursor ->
            while (cursor.moveToNext()) {
                check(!cancelled.get()) { "indexing-cancelled" }
                val uri = cursor.getString(0); val root = cursor.getString(1)
                if (!allowed(root)) continue
                if (!fresh.getOrPut(uri) { try { digest(read(Uri.parse(uri))) == cursor.getString(3) } catch (_: Exception) { false } }) continue
                val text = cursor.getString(5)
                val lexical = words.count { Regex("(?<![\\p{L}\\p{N}_-])${Regex.escape(it)}(?![\\p{L}\\p{N}_-])", RegexOption.IGNORE_CASE).containsMatchIn(text) }.toDouble() / words.size
                val score = if (q == null) lexical else {
                    val buffer = ByteBuffer.wrap(cursor.getBlob(6)).order(ByteOrder.LITTLE_ENDIAN)
                    q.sumOf { it.toDouble() * buffer.float } + .1 * lexical
                }
                if (score < if (q == null) .0001 else .25) continue
                val prior = matches[uri]?.get("score") as? Double ?: Double.NEGATIVE_INFINITY
                if (score > prior) matches[uri] = mapOf("uri" to uri, "root" to root, "name" to cursor.getString(2), "sha" to cursor.getString(3), "line" to cursor.getInt(4), "page" to if (cursor.isNull(7)) null else cursor.getInt(7), "text" to text, "score" to score)
            }
        }
        return matches.values.sortedByDescending { it["score"] as Double }.take(20)
    }
    fun authorize(uri: String, sha: String): Uri {
        val root = db.rawQuery("SELECT root,sha FROM files WHERE uri=? AND issue IS NULL", arrayOf(uri)).use {
            require(it.moveToFirst() && it.getString(1) == sha) { "source-unavailable" }; it.getString(0)
        }
        require(allowed(root) && digest(read(Uri.parse(uri))) == sha) { "source-changed" }
        return Uri.parse(uri)
    }
    fun remove(root: String) {
        db.beginTransaction()
        try {
            db.execSQL("DELETE FROM chunks WHERE uri IN (SELECT uri FROM files WHERE root=?)", arrayOf(root))
            db.delete("files", "root=?", arrayOf(root)); db.delete("roots", "uri=?", arrayOf(root))
            db.setTransactionSuccessful()
        } finally { db.endTransaction() }
        try { resolver.releasePersistableUriPermission(Uri.parse(root), android.content.Intent.FLAG_GRANT_READ_URI_PERMISSION) } catch (_: SecurityException) { }
    }
    override fun close() { model?.close(); helper.close() }
}
