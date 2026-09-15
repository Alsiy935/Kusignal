package com.yasignal.kucoinsignal;

import android.app.Activity;
import android.os.Bundle;
import android.graphics.Color;
import android.graphics.Typeface;
import android.view.Gravity;
import android.widget.*;
import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.util.*;
import org.json.*;

public class MainActivity extends Activity {
    private LinearLayout root;
    private EditText symbol;
    private Button scan;
    private TextView signal, details, status;
    private static final String API = "https://api.kucoin.com/api/ua/v2/market/kline";
    private static final String[] TF = {"5min", "15min", "1hour", "4hour"};
    private static final int[] SEC = {300, 900, 3600, 14400};

    @Override public void onCreate(Bundle b) { super.onCreate(b); build(); }

    private TextView tv(String s, int size) {
        TextView t = new TextView(this);
        t.setText(s); t.setTextColor(Color.WHITE); t.setTextSize(size);
        t.setPadding(20, 12, 20, 12); return t;
    }

    private void build() {
        root = new LinearLayout(this); root.setOrientation(LinearLayout.VERTICAL);
        root.setPadding(24,24,24,24); root.setBackgroundColor(Color.rgb(16,17,20));
        TextView title = tv("Futures Signal",28); title.setTypeface(Typeface.DEFAULT,Typeface.BOLD);
        root.addView(title); root.addView(tv("KuCoin Futures • multi-timeframe",14));
        symbol = new EditText(this); symbol.setText("XBTUSDTM"); symbol.setHint("Futures symbol");
        symbol.setTextColor(Color.WHITE); symbol.setHintTextColor(Color.GRAY); root.addView(symbol);
        scan = new Button(this); scan.setText("ANALYZE"); root.addView(scan);
        signal = tv("WAIT",32); signal.setGravity(Gravity.CENTER); signal.setTypeface(Typeface.DEFAULT,Typeface.BOLD);
        root.addView(signal,new LinearLayout.LayoutParams(-1,110));
        details = tv("Entry —\nSL —\nTP1 —\nTP2 —\nTP3 —",18);
        details.setBackgroundResource(com.yasignal.kucoinsignal.R.drawable.bg); root.addView(details);
        status = tv("Ready",13); root.addView(status);
        scan.setOnClickListener(v -> runScan()); setContentView(root);
    }

    private void runScan() {
        final String s = symbol.getText().toString().trim().toUpperCase(Locale.US);
        if (s.isEmpty()) return;
        scan.setEnabled(false); status.setText("Loading 5m / 15m / 1h / 4h…");
        new Thread(() -> {
            try {
                Map<String,ArrayList<C>> data = new LinkedHashMap<>();
                for (int i=0;i<TF.length;i++) data.put(TF[i], getCandles(s, TF[i], SEC[i]));
                Result r = analyze(data);
                runOnUiThread(() -> show(r));
            } catch (Exception e) {
                final String msg = e.getMessage()==null ? e.toString() : e.getMessage();
                runOnUiThread(() -> { signal.setText("ERROR"); details.setText(msg); status.setText("Request failed"); });
            } finally { runOnUiThread(() -> scan.setEnabled(true)); }
        }).start();
    }

    private ArrayList<C> getCandles(String s, String interval, int seconds) throws Exception {
        String u = API + "?symbol=" + URLEncoder.encode(s,"UTF-8") +
                "&tradeType=FUTURES&klineType=TRADE&interval=" + interval;
        HttpURLConnection x = (HttpURLConnection)new URL(u).openConnection();
        x.setConnectTimeout(10000); x.setReadTimeout(15000); x.setRequestMethod("GET");
        int code = x.getResponseCode();
        InputStream raw = code >= 200 && code < 300 ? x.getInputStream() : x.getErrorStream();
        String body = readAll(raw);
        if (code < 200 || code >= 300) throw new Exception("HTTP " + code + ": " + body);
        JSONObject j = new JSONObject(body);
        if (!"200000".equals(j.optString("code"))) throw new Exception("KuCoin API: " + j.optString("msg", "unknown error"));
        JSONObject d = j.optJSONObject("data");
        if (d == null) throw new Exception("KuCoin: missing data");
        JSONArray list = d.optJSONArray("list");
        if (list == null || list.length() < 60) throw new Exception("KuCoin: not enough candles for " + interval);
        ArrayList<C> out = new ArrayList<>();
        for (int i=0;i<list.length();i++) {
            JSONArray q = list.getJSONArray(i);
            if (q.length() < 6) continue;
            long t = q.getLong(0);
            double o=q.getDouble(1), h=q.getDouble(2), l=q.getDouble(3), c=q.getDouble(4), v=q.getDouble(5);
            out.add(new C(t,o,h,l,c,v));
        }
        // API order is not relied upon: sort by candle start time ascending.
        Collections.sort(out, Comparator.comparingLong(a -> a.t));
        return out;
    }

    private static String readAll(InputStream in) throws IOException {
        if (in == null) return "";
        try (InputStream x=in; ByteArrayOutputStream b=new ByteArrayOutputStream()) {
            byte[] buf=new byte[4096]; int n; while((n=x.read(buf))!=-1) b.write(buf,0,n);
            return b.toString(StandardCharsets.UTF_8.name());
        }
    }

    private double ema(ArrayList<C> c,int n){
        double a=2.0/(n+1),v=c.get(0).cl;
        for(int i=1;i<c.size();i++) v=a*c.get(i).cl+(1-a)*v;
        return v;
    }
    private double atr(ArrayList<C> c,int n){
        double sum=0; int start=Math.max(1,c.size()-n);
        for(int i=start;i<c.size();i++){C x=c.get(i),p=c.get(i-1);sum+=Math.max(x.h-x.l,Math.max(Math.abs(x.h-p.cl),Math.abs(x.l-p.cl)));}
        return sum/Math.max(1,c.size()-start);
    }
    private double rsi(ArrayList<C> c,int n){
        double g=0,l=0; int start=c.size()-n;
        for(int i=start;i<c.size();i++){double d=c.get(i).cl-c.get(i-1).cl;if(d>0)g+=d;else l-=d;}
        if(l==0)return 100; double rs=g/l; return 100-100/(1+rs);
    }
    private double avgVol(ArrayList<C> c,int n){
        int end=c.size()-1,start=Math.max(0,end-n); double v=0; int k=0;
        for(int i=start;i<end;i++){v+=c.get(i).vol;k++;} return k==0?0:v/k;
    }

    private Bias bias(ArrayList<C> c){
        double p=c.get(c.size()-1).cl,e20=ema(c,20),e50=ema(c,50),e200=ema(c,200),r=rsi(c,14);
        int bull=0,bear=0;
        if(e20>e50) bull++; else if(e20<e50) bear++;
        if(p>e200) bull++; else if(p<e200) bear++;
        if(r>=52 && r<=68) bull++; else if(r>=32 && r<=48) bear++;
        if(p>e20) bull++; else if(p<e20) bear++;
        return new Bias(bull,bear,r,atr(c,14),p);
    }

    private Result analyze(Map<String,ArrayList<C>> data){
        Bias b5=bias(data.get("5min")), b15=bias(data.get("15min")), b1=bias(data.get("1hour")), b4=bias(data.get("4hour"));
        int L=0,S=0;
        L += b4.bull*10; S += b4.bear*10;
        L += b1.bull*9;  S += b1.bear*9;
        L += b15.bull*6; S += b15.bear*6;
        L += b5.bull*5;  S += b5.bear*5;
        ArrayList<C> c5=data.get("5min"); C last=c5.get(c5.size()-1), prev=c5.get(c5.size()-2);
        double av=avgVol(c5,20);
        if(last.vol>av){if(last.cl>prev.cl)L+=8; else if(last.cl<prev.cl)S+=8;}
        int score=Math.min(100,Math.max(L,S)); String d="WAIT";
        if(score>=62 && Math.abs(L-S)>=10) d=L>S?"LONG":"SHORT";
        double p=last.cl, a=Math.max(b5.atr, b15.atr*0.5), sl,tp1,tp2,tp3;
        if(d.equals("LONG")){sl=p-1.5*a;double risk=p-sl;tp1=p+risk;tp2=p+2*risk;tp3=p+3*risk;}
        else if(d.equals("SHORT")){sl=p+1.5*a;double risk=sl-p;tp1=p-risk;tp2=p-2*risk;tp3=p-3*risk;}
        else {sl=tp1=tp2=tp3=Double.NaN;}
        return new Result(d,score,L,S,p,sl,tp1,tp2,tp3,b5.rsi,b15.rsi,b1.rsi,b4.rsi);
    }

    private void show(Result r){
        signal.setText(r.d+"  "+r.score+"/100");
        String e=r.d.equals("WAIT")?"No entry — WAIT":String.format(Locale.US,"Entry: %.8f\nSL: %.8f\nTP1: %.8f\nTP2: %.8f\nTP3: %.8f",r.p,r.sl,r.tp1,r.tp2,r.tp3);
        details.setText(e+String.format(Locale.US,"\n\nLONG score: %d\nSHORT score: %d\nRSI 5m/15m/1h/4h: %.1f / %.1f / %.1f / %.1f",r.l,r.s,r.r5,r.r15,r.r1,r.r4));
        status.setText("Updated: "+new Date());
    }

    static class C {long t;double o,h,l,cl,vol;C(long t,double o,double h,double l,double c,double v){this.t=t;this.o=o;this.h=h;this.l=l;cl=c;vol=v;}}
    static class Bias {int bull,bear;double rsi,atr,p;Bias(int b,int s,double r,double a,double p){bull=b;bear=s;rsi=r;atr=a;this.p=p;}}
    static class Result {String d;int score,l,s;double p,sl,tp1,tp2,tp3,r5,r15,r1,r4;Result(String d,int sc,int l,int s,double p,double sl,double a,double b,double c,double r5,double r15,double r1,double r4){this.d=d;score=sc;this.l=l;this.s=s;this.p=p;this.sl=sl;tp1=a;tp2=b;tp3=c;this.r5=r5;this.r15=r15;this.r1=r1;this.r4=r4;}}
}
