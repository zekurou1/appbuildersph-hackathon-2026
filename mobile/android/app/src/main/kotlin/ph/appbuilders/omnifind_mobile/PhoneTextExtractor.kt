package ph.appbuilders.omnifind_mobile

import android.content.Context
import android.graphics.pdf.PdfRenderer
import android.os.Build
import android.os.ParcelFileDescriptor
import java.io.File
import java.nio.ByteBuffer
import java.nio.charset.CodingErrorAction

data class SourceLine(val page: Int?, val line: Int, val text: String)

/** Bounded, phone-local extraction. PDF evidence refers to extracted page text, not visual rows. */
class PhoneTextExtractor(private val context: Context) {
    private val staging = File(context.cacheDir, "omnifind-pdf").apply { mkdirs() }
    init { staging.listFiles()?.filter { it.name.startsWith("source-") && it.extension == "pdf" }?.forEach { it.delete() } }

    fun extract(name: String, bytes: ByteArray, checkpoint: () -> Unit): List<SourceLine> {
        checkpoint()
        require(bytes.size <= 1_048_576) { "file-too-large" }
        if (!name.endsWith(".pdf", ignoreCase = true)) {
            require(name.endsWith(".txt", true) || name.endsWith(".md", true)) { "unsupported-type" }
            val decoder = Charsets.UTF_8.newDecoder().onMalformedInput(CodingErrorAction.REPORT).onUnmappableCharacter(CodingErrorAction.REPORT)
            return decoder.decode(ByteBuffer.wrap(bytes)).toString().lines().mapIndexed { index, text -> SourceLine(null, index + 1, text) }
        }
        require(Build.VERSION.SDK_INT >= 35) { "pdf-needs-android-15" }
        return extractPdf(bytes, checkpoint)
    }

    @android.annotation.TargetApi(35)
    private fun extractPdf(bytes: ByteArray, checkpoint: () -> Unit): List<SourceLine> {
        val file = File.createTempFile("source-", ".pdf", staging)
        try {
            file.writeBytes(bytes)
            return ParcelFileDescriptor.open(file, ParcelFileDescriptor.MODE_READ_ONLY).use { descriptor ->
                PdfRenderer(descriptor).use { renderer ->
                    require(renderer.pageCount in 1..20) { "pdf-page-limit" }
                    var characters = 0
                    val lines = mutableListOf<SourceLine>()
                    for (pageNumber in 0 until renderer.pageCount) {
                        checkpoint()
                        renderer.openPage(pageNumber).use { page ->
                            var lineNumber = 0
                            for (content in page.textContents) {
                                checkpoint()
                                characters += content.text.length
                                require(characters <= 100_000) { "pdf-text-limit" }
                                for (line in content.text.lines()) lines.add(SourceLine(pageNumber + 1, ++lineNumber, line))
                            }
                        }
                    }
                    require(lines.any { it.text.isNotBlank() }) { "pdf-no-text" }
                    lines
                }
            }
        } catch (error: Exception) {
            if (error.message in setOf("pdf-page-limit", "pdf-text-limit", "pdf-no-text", "indexing-cancelled", "folder-unavailable")) throw error
            throw IllegalArgumentException("pdf-unreadable")
        } finally { file.delete() }
    }
}
