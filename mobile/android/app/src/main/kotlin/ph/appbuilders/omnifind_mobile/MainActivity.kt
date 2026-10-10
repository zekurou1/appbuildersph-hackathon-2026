package ph.appbuilders.omnifind_mobile

import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel
import android.content.Intent
import android.net.Uri
import android.os.Handler
import android.os.Looper
import java.util.concurrent.Executors
import java.util.concurrent.atomic.AtomicBoolean

class MainActivity : FlutterActivity() {
    private val executor = Executors.newSingleThreadExecutor()
    private val main = Handler(Looper.getMainLooper())
    private val cancel = AtomicBoolean(false)
    private var picker: MethodChannel.Result? = null
    private val index by lazy { PhoneIndex(this) }
    override fun configureFlutterEngine(engine: FlutterEngine) {
        super.configureFlutterEngine(engine)
        MethodChannel(engine.dartExecutor.binaryMessenger, "omnifind/phone").setMethodCallHandler { call, result ->
            if (call.method == "cancel") { cancel.set(true); result.success(null); return@setMethodCallHandler }
            if (call.method == "pick") {
                if (picker != null) { result.error("picker-busy", "Finish the current picker.", null); return@setMethodCallHandler }
                picker = result
                startActivityForResult(Intent(Intent.ACTION_OPEN_DOCUMENT_TREE).addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_GRANT_PERSISTABLE_URI_PERMISSION), 841)
                return@setMethodCallHandler
            }
            if (call.method in setOf("refresh", "search")) cancel.set(false)
            executor.execute {
                try {
                    val value: Any? = when (call.method) {
                        "roots" -> index.roots()
                        "refresh" -> index.refresh(call.argument<String>("root")!!, cancel)
                        "search" -> index.search(call.argument<String>("query")!!, call.argument<Boolean>("wordsOnly") ?: false, cancel)
                        "remove" -> { index.remove(call.argument<String>("root")!!); null }
                        "open" -> {
                            val uri = index.authorize(call.argument<String>("uri")!!, call.argument<String>("sha")!!)
                            main.post {
                                try {
                                    startActivity(Intent(Intent.ACTION_VIEW).setDataAndType(uri, contentResolver.getType(uri) ?: "text/plain").addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION))
                                    result.success(null)
                                } catch (_: Exception) { result.error("open-unavailable", "No viewer is available for this file.", null) }
                            }
                            return@execute
                        }
                        else -> throw IllegalArgumentException("unknown-action")
                    }
                    main.post { result.success(value) }
                } catch (error: Exception) {
                    val code = error.message?.takeIf { it.matches(Regex("[a-z-]{1,80}")) } ?: "local-operation-failed"
                    main.post { result.error(code, "The local operation could not finish. Refresh the folder or choose it again.", null) }
                }
            }
        }
    }
    @Deprecated("Platform picker bridge")
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        if (requestCode != 841) return
        val response = picker ?: return
        picker = null
        val uri = data?.data
        if (resultCode != RESULT_OK || uri == null) { response.success(null); return }
        if (uri.authority != "com.android.externalstorage.documents") {
            response.error("choose-local-storage", "Choose a folder on this phone. Cloud providers are not supported.", null); return
        }
        try {
            contentResolver.takePersistableUriPermission(uri, Intent.FLAG_GRANT_READ_URI_PERMISSION)
            executor.execute {
                try { index.add(uri); main.post { response.success(uri.toString()) } }
                catch (_: Exception) { main.post { response.error("folder-unavailable", "Choose the folder again.", null) } }
            }
        } catch (_: SecurityException) { response.error("permission-denied", "Folder access was not granted. Choose it again.", null) }
    }
    override fun onDestroy() {
        cancel.set(true)
        executor.execute { index.close() }
        executor.shutdown()
        super.onDestroy()
    }
}
