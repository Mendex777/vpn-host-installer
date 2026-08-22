package ru.metadmin.relay;

import android.content.Intent;
import android.content.SharedPreferences;
import android.net.VpnService;
import android.os.Bundle;
import android.text.InputType;
import android.view.View;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.TextView;
import androidx.appcompat.app.AppCompatActivity;
import androidx.core.content.ContextCompat;

public class MainActivity extends AppCompatActivity {
    private static final int VPN_REQUEST = 7;
    private EditText relay, key;
    private TextView status;

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        SharedPreferences p = getSharedPreferences("relay", MODE_PRIVATE);
        LinearLayout box = new LinearLayout(this);
        box.setOrientation(LinearLayout.VERTICAL); box.setPadding(40, 60, 40, 40);
        TextView title = new TextView(this); title.setText("Metadmin Relay"); title.setTextSize(28); box.addView(title);
        relay = new EditText(this); relay.setHint("https://relay.example.com"); relay.setText(p.getString("url", "https://relay-reg.metadmin.ru")); box.addView(relay);
        key = new EditText(this); key.setHint("Ключ доступа"); key.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_PASSWORD); key.setText(p.getString("key", "")); box.addView(key);
        Button connect = new Button(this); connect.setText("Подключить"); connect.setOnClickListener(v -> prepare()); box.addView(connect);
        Button stop = new Button(this); stop.setText("Отключить"); stop.setOnClickListener(v -> { Intent i=new Intent(this, RelayVpnService.class); i.setAction(RelayVpnService.STOP); startService(i); status.setText("Отключено"); }); box.addView(stop);
        status = new TextView(this); status.setText("Готово к подключению"); status.setTextSize(17); status.setPadding(0,30,0,0); box.addView(status);
        setContentView(box);
    }

    private void prepare() {
        String url=relay.getText().toString().trim(), token=key.getText().toString().trim();
        if (!url.startsWith("https://") || token.isEmpty()) { status.setText("Укажите HTTPS-адрес и ключ"); return; }
        getSharedPreferences("relay", MODE_PRIVATE).edit().putString("url", url.replaceAll("/+$", "")).putString("key", token).apply();
        Intent permission=VpnService.prepare(this);
        if (permission != null) startActivityForResult(permission, VPN_REQUEST); else startVpn();
    }
    @Override protected void onActivityResult(int request, int result, Intent data) { super.onActivityResult(request,result,data); if(request==VPN_REQUEST && result==RESULT_OK) startVpn(); }
    private void startVpn() { Intent i=new Intent(this, RelayVpnService.class); i.setAction(RelayVpnService.START); ContextCompat.startForegroundService(this,i); status.setText("Подключение запущено"); }
}
