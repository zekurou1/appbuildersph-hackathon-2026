package ph.appbuilders.omnifind_mobile

import android.graphics.Paint
import android.content.ContextWrapper
import android.database.DatabaseErrorHandler
import android.database.sqlite.SQLiteDatabase
import android.graphics.pdf.PdfDocument
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.ext.junit.runners.AndroidJUnit4
import org.junit.Test
import org.junit.Assert.*
import org.junit.runner.RunWith
import java.io.ByteArrayOutputStream
import java.io.File

@RunWith(AndroidJUnit4::class)
class PhonePdfTest {
    private val context get() = InstrumentationRegistry.getInstrumentation().targetContext
    private fun pdf(vararg pages: String): ByteArray {
        val document = PdfDocument()
        try {
            for ((index, text) in pages.withIndex()) {
                val page = document.startPage(PdfDocument.PageInfo.Builder(600, 800, index + 1).create())
                page.canvas.drawText(text, 40f, 80f, Paint().apply { textSize = 18f })
                document.finishPage(page)
            }
            return ByteArrayOutputStream().also { document.writeTo(it) }.toByteArray()
        } finally { document.close() }
    }
    private fun rejected(expected: String, action: () -> Unit) {
        try { action(); fail("Expected $expected") } catch (error: IllegalArgumentException) { assertEquals(expected, error.message) }
    }
    private fun noStagingFiles() = assertTrue(File(context.cacheDir, "omnifind-pdf").listFiles().orEmpty().isEmpty())

    @Test fun digitalPdfPreservesPageAndSupportsMeaningSearch() {
        val lines = PhoneTextExtractor(context).extract("agreement.PDF", pdf("Physics timetable on Wednesday.", "Rental deposit returned thirty days after moving out.")) {}
        assertTrue(lines.any { it.page == 2 && it.text.contains("Rental deposit") })
        PhoneEmbedder(context).use { model ->
            val query = model.embed("How soon do I get my rental deposit after leaving?")
            fun score(page: Int): Double {
                val vector = model.embed(lines.filter { it.page == page }.joinToString(" ") { it.text })
                return vector.indices.sumOf { query[it].toDouble() * vector[it] }
            }
            assertTrue(score(2) > score(1))
        }
        noStagingFiles()
    }
    @Test fun emptyAndMalformedPdfsAreExplicitIssues() {
        val extractor = PhoneTextExtractor(context)
        rejected("pdf-no-text") { extractor.extract("scan.pdf", pdf("")) {} }
        rejected("pdf-unreadable") { extractor.extract("broken.pdf", "not a PDF".toByteArray()) {} }
        noStagingFiles()
    }
    @Test fun oversizedPageCountIsRejectedWithoutPartialText() {
        rejected("pdf-page-limit") { PhoneTextExtractor(context).extract("long.pdf", pdf(*Array(21) { "Page $it" })) {} }
        noStagingFiles()
    }
    @Test fun cancelledPdfDeletesTemporaryCopy() {
        var checkpoints = 0
        try {
            PhoneTextExtractor(context).extract("cancel.pdf", pdf("Rental deposit")) { if (++checkpoints == 2) error("indexing-cancelled") }
            fail("Expected cancellation")
        } catch (error: IllegalStateException) { assertEquals("indexing-cancelled", error.message) }
        noStagingFiles()
    }
    @Test fun textLinesRetainOriginalNumbersAndHaveNoPdfPage() {
        val lines = PhoneTextExtractor(context).extract("receipt.md", "Header\n\nReceipt PKG-483".toByteArray()) {}
        assertEquals(3, lines.last().line)
        assertNull(lines.last().page)
        assertEquals("Receipt PKG-483", lines.last().text)
    }
    @Test fun existingTextIndexMigratesWithoutDeletingPassages() {
        // Dedicated test file; never the production phone-index.sqlite database.
        val testFile = File.createTempFile("migration-test-", ".sqlite", context.cacheDir)
        val testContext = object : ContextWrapper(context) {
            override fun getDatabasePath(name: String) = testFile
            override fun openOrCreateDatabase(name: String, mode: Int, factory: SQLiteDatabase.CursorFactory?): SQLiteDatabase =
                SQLiteDatabase.openOrCreateDatabase(testFile.path, factory)
            override fun openOrCreateDatabase(name: String, mode: Int, factory: SQLiteDatabase.CursorFactory?, errorHandler: DatabaseErrorHandler?): SQLiteDatabase =
                SQLiteDatabase.openOrCreateDatabase(testFile.path, factory, errorHandler)
        }
        try {
            testContext.openOrCreateDatabase("phone-index.sqlite", 0, null).use { db ->
                db.execSQL("CREATE TABLE roots(uri TEXT PRIMARY KEY,name TEXT NOT NULL)")
                db.execSQL("CREATE TABLE files(uri TEXT PRIMARY KEY,root TEXT NOT NULL,name TEXT NOT NULL,sha TEXT NOT NULL,issue TEXT)")
                db.execSQL("CREATE TABLE chunks(uri TEXT NOT NULL,line INTEGER NOT NULL,text TEXT NOT NULL,vector BLOB NOT NULL)")
                db.execSQL("INSERT INTO chunks VALUES ('synthetic',3,'Receipt PKG-483',X'00')")
                db.version = 1
            }
            PhoneIndex(testContext).use { assertNotNull(it.roots()) }
            testContext.openOrCreateDatabase("phone-index.sqlite", 0, null).use { db ->
                assertEquals(2, db.version)
                db.rawQuery("SELECT line,text,page FROM chunks", null).use { row ->
                    assertTrue(row.moveToFirst())
                    assertEquals(3, row.getInt(0))
                    assertEquals("Receipt PKG-483", row.getString(1))
                    assertTrue(row.isNull(2))
                }
            }
        } finally { testFile.delete() }
    }
}
