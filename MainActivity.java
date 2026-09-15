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
    private static final String API="https://api.kucoin.com/api/ua/v2/market/";
    private static final String[] TF={"5min","15min","1hour","4hour"};
    private static final int[] SEC={300,900,3600,14400};

    @Override public void onCreate(Bundle b){ super.onCreate(b); build(); }
    private TextView tv(String s,int size){
        TextView t=new TextView(this); t.setText(s); t.setTextColor(Color.WHITE); t.setTextSize(size); t.setPadding(20,12,20,12); return t;
    }
    private void build(){
        ScrollView scroll=new ScrollView(this);
        root=new LinearLayout(this); root.setOrientation(LinearLayout.VERTICAL); root.setPadding(24,24,24,24); root.setBackgroundColor(Color.rgb(16,17,20));
        TextView title=tv("Futures Signal PRO",28); title.setTypeface(Typeface.DEFAULT,Typeface.BOLD); root.addView(title);
        root.addView(tv("KuCoin Futures • trend + momentum + structure + volume + order book + OI/funding",13));
        symbol=new EditText(this); symbol.setText("XBTUSDTM"); symbol.setHint("Futures symbol"); symbol.setTextColor(Color.WHITE); symbol.setHintTextColor(Color.GRAY); root.addView(symbol);
        scan=new Button(this); scan.setText("ANALYZE"); root.addView(scan);
        signal=tv("WAIT",32); signal.setGravity(Gravity.CENTER); signal.setTypeface(Typeface.DEFAULT,Typeface.BOLD); root.addView(signal,new LinearLayout.LayoutParams(-1,110));
        details=tv("Entry —\nSL —\nTP1 —\nTP2 —\nTP3 —",17); details.setBackgroundResource(com.yasignal.kucoinsignal.R.drawable.bg); root.addView(details);
        status=tv("Ready",13); root.addView(status);
        scan.setOnClickListener(v->runScan());
        scroll.addView(root); setContentView(scroll);
    }

    private void runScan(){
        final String s=symbol.getText().toString().trim().toUpperCase(Locale.US); if(s.isEmpty()) return;
        scan.setEnabled(false); status.setText("Loading candles, order book, OI and funding…");
        new Thread(()->{
            try{
                Map<String,ArrayList<C>> data=new LinkedHashMap<>();
                for(int i=0;i<TF.length;i++) data.put(TF[i],getCandles(s,TF[i],SEC[i]));
                MarketExtras ex=getExtras(s);
                Result r=analyze(data,ex);
                runOnUiThread(()->show(r));
            }catch(Exception e){
                String m=e.getMessage()==null?e.toString():e.getMessage();
                runOnUiThread(()->{ signal.setText("ERROR"); details.setText(m); status.setText("Request failed"); });
            } finally { runOnUiThread(()->scan.setEnabled(true)); }
        }).start();
    }

    private ArrayList<C> getCandles(String s,String interval,int sec)throws Exception{
        String u=API+"kline?symbol="+URLEncoder.encode(s,"UTF-8")+"&tradeType=FUTURES&klineType=TRADE&interval="+interval;
        JSONObject j=getJson(u); JSONObject d=j.optJSONObject("data"); JSONArray list=d==null?null:d.optJSONArray("list");
        if(list==null||list.length()<80) throw new Exception("Not enough candles for "+interval);
        ArrayList<C> out=new ArrayList<>();
        for(int i=0;i<list.length();i++){
            JSONArray q=list.getJSONArray(i); if(q.length()<6) continue;
            out.add(new C(q.getLong(0),q.getDouble(1),q.getDouble(2),q.getDouble(3),q.getDouble(4),q.getDouble(5)));
        }
        Collections.sort(out,Comparator.comparingLong(a->a.t));
        long now=System.currentTimeMillis()/1000;
        if(out.size()>2 && now-out.get(out.size()-1).t<sec) out.remove(out.size()-1);
        if(out.size()<80) throw new Exception("Not enough closed candles for "+interval);
        return out;
    }

    private MarketExtras getExtras(String s)throws Exception{
        double bid=0,ask=0,oi=Double.NaN,prevOi=Double.NaN,funding=Double.NaN;
        try{
            JSONObject j=getJson(API+"orderbook?tradeType=FUTURES&symbol="+URLEncoder.encode(s,"UTF-8")+"&limit=20");
            JSONObject d=j.optJSONObject("data"); bid=sideSum(d==null?null:d.optJSONArray("bids")); ask=sideSum(d==null?null:d.optJSONArray("asks"));
        }catch(Exception ignored){}
        try{
            // Use a 30-minute OI window (6 x 5m), rather than a single 5m jump.
            JSONObject j=getJson(API+"open-interest?symbol="+URLEncoder.encode(s,"UTF-8")+"&interval=5min&pageSize=7");
            JSONArray a=j.optJSONArray("data");
            if(a!=null&&a.length()>0){
                ArrayList<double[]> pts=new ArrayList<>();
                for(int i=0;i<a.length();i++){
                    JSONObject o=a.getJSONObject(i); double v=number(o,"openInterest");
                    long ts=o.optLong("ts",0); if(!Double.isNaN(v)&&ts>0)pts.add(new double[]{ts,v});
                }
                Collections.sort(pts,Comparator.comparingDouble(x->x[0]));
                if(!pts.isEmpty()){
                    oi=pts.get(pts.size()-1)[1];
                    int ref=Math.max(0,pts.size()-7);
                    prevOi=pts.get(ref)[1];
                }
            }
        }catch(Exception ignored){}
        try{
            // KuCoin's current UTA V2 example accepts symbol together with productType=COIN-FUTURES for XBTUSDTM.
            JSONObject j=getJson(API+"funding-rate?symbol="+URLEncoder.encode(s,"UTF-8")+"&productType=COIN-FUTURES");
            JSONArray a=j.optJSONArray("data"); if(a!=null&&a.length()>0) funding=number(a.getJSONObject(0),"nextFundingRate");
        }catch(Exception ignored){}
        return new MarketExtras(bid,ask,oi,prevOi,funding);
    }
    private double number(JSONObject o,String key){
        Object v=o.opt(key); if(v==null||v==JSONObject.NULL)return Double.NaN;
        try{return Double.parseDouble(String.valueOf(v));}catch(Exception e){return Double.NaN;}
    }
    private double sideSum(JSONArray a){ double x=0; if(a==null)return 0; for(int i=0;i<Math.min(20,a.length());i++){try{x+=Double.parseDouble(a.getJSONArray(i).getString(1));}catch(Exception ignored){}} return x; }
    private JSONObject getJson(String u)throws Exception{
        HttpURLConnection x=(HttpURLConnection)new URL(u).openConnection(); x.setConnectTimeout(10000); x.setReadTimeout(15000); x.setRequestMethod("GET");
        int code=x.getResponseCode(); String body=readAll(code>=200&&code<300?x.getInputStream():x.getErrorStream());
        if(code<200||code>=300) throw new Exception("HTTP "+code);
        JSONObject j=new JSONObject(body); if(!"200000".equals(j.optString("code"))) throw new Exception("KuCoin: "+j.optString("msg","API error")); return j;
    }
    private static String readAll(InputStream in)throws IOException{ if(in==null)return""; try(InputStream x=in;ByteArrayOutputStream b=new ByteArrayOutputStream()){byte[] z=new byte[4096];int n;while((n=x.read(z))!=-1)b.write(z,0,n);return b.toString(StandardCharsets.UTF_8.name());} }

    private double ema(ArrayList<C> c,int n){ return emaAt(c,n,c.size()-1); }
    private double emaAt(ArrayList<C> c,int n,int end){
        if(end<0)return Double.NaN; double a=2.0/(n+1),v=c.get(0).cl; for(int i=1;i<=end;i++)v=a*c.get(i).cl+(1-a)*v; return v;
    }
    private double atr(ArrayList<C> c,int n){
        int start=Math.max(1,c.size()-n); double s=0; for(int i=start;i<c.size();i++){C x=c.get(i),p=c.get(i-1);s+=Math.max(x.h-x.l,Math.max(Math.abs(x.h-p.cl),Math.abs(x.l-p.cl)));} return s/Math.max(1,c.size()-start);
    }
    private double rsi(ArrayList<C> c,int n){
        if(c.size()<n+1)return 50; int start=c.size()-n; double gain=0,loss=0;
        for(int i=start;i<c.size();i++){double d=c.get(i).cl-c.get(i-1).cl;if(d>0)gain+=d;else loss-=d;}
        if(loss==0)return gain==0?50:100; double rs=gain/loss; return 100-100/(1+rs);
    }
    private double macdHist(ArrayList<C> c){
        int end=c.size()-1; double a12=2.0/13.0,a26=2.0/27.0; double e12=c.get(0).cl,e26=c.get(0).cl;
        ArrayList<Double> macd=new ArrayList<>();
        for(int i=1;i<=end;i++){e12=a12*c.get(i).cl+(1-a12)*e12;e26=a26*c.get(i).cl+(1-a26)*e26;macd.add(e12-e26);}
        if(macd.size()<9)return macd.get(macd.size()-1);
        double a9=2.0/10.0,signal=macd.get(0); for(int i=1;i<macd.size();i++)signal=a9*macd.get(i)+(1-a9)*signal;
        return macd.get(macd.size()-1)-signal;
    }
    private double adx(ArrayList<C> c,int n){
        if(c.size()<n*2+2)return 0;
        ArrayList<Double> tr=new ArrayList<>(),plus=new ArrayList<>(),minus=new ArrayList<>();
        for(int i=1;i<c.size();i++){
            C x=c.get(i),p=c.get(i-1); double range=Math.max(x.h-x.l,Math.max(Math.abs(x.h-p.cl),Math.abs(x.l-p.cl)));
            double up=x.h-p.h,down=p.l-x.l; tr.add(range); plus.add(up>down&&up>0?up:0); minus.add(down>up&&down>0?down:0);
        }
        double atr=0,pdm=0,mdm=0; for(int i=0;i<n;i++){atr+=tr.get(i);pdm+=plus.get(i);mdm+=minus.get(i);} atr/=n;pdm/=n;mdm/=n;
        ArrayList<Double> dx=new ArrayList<>();
        for(int i=n;i<tr.size();i++){
            atr=((atr*(n-1))+tr.get(i))/n; pdm=((pdm*(n-1))+plus.get(i))/n; mdm=((mdm*(n-1))+minus.get(i))/n;
            double pdi=atr==0?0:100*pdm/atr,mdi=atr==0?0:100*mdm/atr; dx.add(100*Math.abs(pdi-mdi)/Math.max(0.0001,pdi+mdi));
        }
        if(dx.size()<n)return dx.isEmpty()?0:dx.get(dx.size()-1); double adx=0; for(int i=0;i<n;i++)adx+=dx.get(i);adx/=n;
        for(int i=n;i<dx.size();i++)adx=((adx*(n-1))+dx.get(i))/n; return adx;
    }
    private double avgVol(ArrayList<C> c,int n){int e=c.size()-1,st=Math.max(0,e-n);double s=0;for(int i=st;i<e;i++)s+=c.get(i).vol;return s/Math.max(1,e-st);}
    private double highest(ArrayList<C> c,int n){double x=-Double.MAX_VALUE;for(int i=Math.max(0,c.size()-n);i<c.size();i++)x=Math.max(x,c.get(i).h);return x;}
    private double lowest(ArrayList<C> c,int n){double x=Double.MAX_VALUE;for(int i=Math.max(0,c.size()-n);i<c.size();i++)x=Math.min(x,c.get(i).l);return x;}
    private int clamp(int x){return Math.max(0,Math.min(100,x));}

    private Bias bias(ArrayList<C> c){
        double p=c.get(c.size()-1).cl,e20=ema(c,20),e50=ema(c,50),e200=ema(c,Math.min(200,c.size())),r=rsi(c,14),a=atr(c,14),ad=adx(c,14),mh=macdHist(c); int l=0,s=0;
        if(p>e20)l+=2;else s+=2; if(e20>e50)l+=3;else s+=3; if(p>e200)l+=3;else s+=3;
        if(r>55)l+=2;else if(r<45)s+=2; if(mh>0)l+=2;else if(mh<0)s+=2;
        if(ad>=20){if(p>e50)l+=2;else s+=2;}
        return new Bias(l,s,r,a,ad,e20,e50,e200);
    }

    private Result analyze(Map<String,ArrayList<C>> d,MarketExtras ex){
        Bias b5=bias(d.get("5min")),b15=bias(d.get("15min")),b1=bias(d.get("1hour")),b4=bias(d.get("4hour"));
        int L=b4.l*5+b1.l*4+b15.l*3+b5.l*2, S=b4.s*5+b1.s*4+b15.s*3+b5.s*2;
        ArrayList<C> c5=d.get("5min"),c15=d.get("15min"),c1=d.get("1hour"); C z=c5.get(c5.size()-1),p=c5.get(c5.size()-2); double av=avgVol(c5,20),vr=av==0?1:z.vol/av;
        if(vr>=1.5){if(z.cl>p.cl)L+=8;else if(z.cl<p.cl)S+=8;}
        double r15h=highest(c15,30),r15l=lowest(c15,30),r1h=highest(c1,30),r1l=lowest(c1,30),price=z.cl;
        if(price>=r15h*0.999)L+=7; if(price<=r15l*1.001)S+=7; if(price>=r1h*0.999)L+=5; if(price<=r1l*1.001)S+=5;
        double imb=(ex.bid+ex.ask)==0?0:(ex.bid-ex.ask)/(ex.bid+ex.ask); if(imb>0.15)L+=5; else if(imb<-0.15)S+=5;
        double oiDelta=Double.NaN; if(!Double.isNaN(ex.oi)&&!Double.isNaN(ex.prevOi)&&ex.prevOi!=0)oiDelta=(ex.oi-ex.prevOi)/ex.prevOi;
        // Compare price over the same ~30-minute window as OI when possible.
        int priceRef=Math.max(0,c5.size()-7);
        C priceBase=c5.get(priceRef);
        double priceDelta=(z.cl-priceBase.cl)/Math.max(0.00000001,priceBase.cl);
        if(!Double.isNaN(oiDelta)&&Math.abs(oiDelta)>=0.001){
            if(priceDelta>0&&oiDelta>0)L+=6; else if(priceDelta<0&&oiDelta>0)S+=6;
            else if(priceDelta>0&&oiDelta<0)L+=2; else if(priceDelta<0&&oiDelta<0)S+=2;
        }
        if(!Double.isNaN(ex.funding)){if(ex.funding>0.0015)S+=3;else if(ex.funding<-0.0015)L+=3;}
        int max=Math.max(L,S),min=Math.min(L,S),score=clamp((int)Math.round(max*100.0/120.0));
        boolean trendAligned=(b4.l>=8&&b1.l>=8)||(b4.s>=8&&b1.s>=8), strong=max-min>=10; String dir="WAIT";
        if(score>=65&&strong&&trendAligned)dir=L>S?"LONG":"SHORT";
        double atr=Math.max(b5.a,b15.a*0.7),entry=price,sl,tp1,tp2,tp3,swingL=lowest(c15,20),swingH=highest(c15,20);
        if(dir.equals("LONG")){sl=Math.min(swingL,entry-1.4*atr);if(sl>=entry)sl=entry-1.5*atr;double risk=entry-sl;tp1=entry+1.2*risk;tp2=entry+2*risk;tp3=entry+3*risk;}
        else if(dir.equals("SHORT")){sl=Math.max(swingH,entry+1.4*atr);if(sl<=entry)sl=entry+1.5*atr;double risk=sl-entry;tp1=entry-1.2*risk;tp2=entry-2*risk;tp3=entry-3*risk;}
        else sl=tp1=tp2=tp3=Double.NaN;
        return new Result(dir,score,L,S,entry,sl,tp1,tp2,tp3,b5,b15,b1,b4,vr,imb,ex.funding,oiDelta);
    }

    private void show(Result r){
        signal.setText(r.d+"  "+r.score+"/100");
        String e=r.d.equals("WAIT")?"NO ENTRY — WAIT":String.format(Locale.US,"Entry: %.8f\nSL: %.8f\nTP1: %.8f\nTP2: %.8f\nTP3: %.8f",r.p,r.sl,r.tp1,r.tp2,r.tp3);
        String oi=Double.isNaN(r.oiDelta)?"N/A":String.format(Locale.US,"%+.2f%%",r.oiDelta*100);
        details.setText(e+String.format(Locale.US,"\n\nLONG: %d   SHORT: %d\nRSI 5m/15m/1h/4h: %.1f / %.1f / %.1f / %.1f\nVolume x avg: %.2f\nOrder-book imbalance: %.2f\nOI change ~30m: %s\nFunding: %s\n\nFilters: EMA20/50/200 • RSI • MACD • Wilder ADX • swing structure • volume • order book • OI delta • funding",r.l,r.s,r.b5.rsi,r.b15.rsi,r.b1.rsi,r.b4.rsi,r.vr,r.imb,oi,Double.isNaN(r.funding)?"N/A":String.format(Locale.US,"%.5f%%",r.funding*100)));
        status.setText("Updated: "+new Date()+" • closed candles only • 4h+1h trend alignment required");
    }

    static class C{long t;double o,h,l,cl,vol;C(long t,double o,double h,double l,double c,double v){this.t=t;this.o=o;this.h=h;this.l=l;cl=c;vol=v;}}
    static class Bias{int l,s;double rsi,a,adx,e20,e50,e200;Bias(int l,int s,double r,double a,double ad,double e20,double e50,double e200){this.l=l;this.s=s;rsi=r;this.a=a;adx=ad;this.e20=e20;this.e50=e50;this.e200=e200;}}
    static class MarketExtras{double bid,ask,oi,prevOi,funding;MarketExtras(double b,double a,double oi,double prev,double f){bid=b;ask=a;this.oi=oi;prevOi=prev;funding=f;}}
    static class Result{String d;int score,l,s;double p,sl,tp1,tp2,tp3,vr,imb,funding,oiDelta;Bias b5,b15,b1,b4;Result(String d,int sc,int l,int s,double p,double sl,double a,double b,double c,Bias b5,Bias b15,Bias b1,Bias b4,double vr,double imb,double f,double oi){this.d=d;score=sc;this.l=l;this.s=s;this.p=p;this.sl=sl;tp1=a;tp2=b;tp3=c;this.b5=b5;this.b15=b15;this.b1=b1;this.b4=b4;this.vr=vr;this.imb=imb;funding=f;oiDelta=oi;}}
}
