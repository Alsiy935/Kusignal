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
    private static final String[] TF={"5min","15min","1hour","4hour","1day"};
    private static final int[] SEC={300,900,3600,14400,86400};

    @Override public void onCreate(Bundle b){ super.onCreate(b); build(); }
    private TextView tv(String s,int size){
        TextView t=new TextView(this); t.setText(s); t.setTextColor(Color.WHITE); t.setTextSize(size); t.setPadding(20,12,20,12); return t;
    }
    private void build(){
        ScrollView scroll=new ScrollView(this);
        root=new LinearLayout(this); root.setOrientation(LinearLayout.VERTICAL); root.setPadding(24,44,24,24); root.setBackgroundColor(Color.rgb(16,17,20));
        TextView title=tv("Сигнал фьючерсов PRO v6.1",27); title.setTypeface(Typeface.DEFAULT,Typeface.BOLD); root.addView(title);
        root.addView(tv("Многоуровневая проверка • 1D + 4H + 1H + 15M + 5M • цена + объём + OI + стакан",13));
        symbol=new EditText(this); symbol.setText("XBTUSDTM"); symbol.setHint("Символ фьючерса"); symbol.setTextColor(Color.WHITE); symbol.setHintTextColor(Color.GRAY); root.addView(symbol);
        scan=new Button(this); scan.setText("АНАЛИЗ"); root.addView(scan);
        signal=tv("ОЖИДАНИЕ",32); signal.setGravity(Gravity.CENTER); signal.setTypeface(Typeface.DEFAULT,Typeface.BOLD); root.addView(signal,new LinearLayout.LayoutParams(-1,110));
        details=tv("Вход —\nСтоп-лосс —\nТейк-профит 1 —\nТейк-профит 2 —\nТейк-профит 3 —",17); details.setBackgroundResource(com.yasignal.kucoinsignal.R.drawable.bg); root.addView(details);
        status=tv("Готово",13); root.addView(status);
        scan.setOnClickListener(v->runScan());
        scroll.addView(root); setContentView(scroll);
    }

    private void runScan(){
        final String s=symbol.getText().toString().trim().toUpperCase(Locale.US); if(s.isEmpty()) return;
        scan.setEnabled(false); status.setText("Проверка 1D/4H/1H/15M/5M + рынок + OI…");
        new Thread(()->{
            try{
                Map<String,ArrayList<C>> data=new LinkedHashMap<>();
                for(int i=0;i<TF.length;i++) data.put(TF[i],getCandles(s,TF[i],SEC[i]));
                MarketExtras ex=getExtras(s);
                Result r=analyze(data,ex);
                runOnUiThread(()->show(r));
            }catch(Exception e){
                String m=e.getMessage()==null?e.toString():e.getMessage();
                runOnUiThread(()->{ signal.setText("ОШИБКА"); details.setText(m); status.setText("Не удалось получить полный набор данных — вход заблокирован"); });
            } finally { runOnUiThread(()->scan.setEnabled(true)); }
        }).start();
    }

    private ArrayList<C> getCandles(String s,String interval,int sec)throws Exception{
        // KuCoin Futures REST returns at most 200 candles per request.
        // Request a full 200-candle time window instead of relying on the API default range.
        long now=System.currentTimeMillis()/1000;
        ArrayList<C> out=new ArrayList<>();
        Exception last=null;
        long[] windows={200L,400L,800L};
        for(long count:windows){
            try{
                long end=now;
                long start=now-count*sec;
                String base=API+"kline?symbol="+URLEncoder.encode(s,"UTF-8")+"&tradeType=FUTURES&klineType=TRADE&interval="+interval;
                String u=base+"&startAt="+start+"&endAt="+end;
                JSONObject j=getJson(u); JSONArray list=j.optJSONArray("data");
                if(list==null) continue;
                for(int i=0;i<list.length();i++){
                    JSONArray q=list.getJSONArray(i); if(q.length()<6) continue;
                    out.add(new C(q.getLong(0),q.getDouble(1),q.getDouble(2),q.getDouble(3),q.getDouble(4),q.getDouble(5)));
                }
                Collections.sort(out,Comparator.comparingLong(a->a.t));
                ArrayList<C> unique=new ArrayList<>(); long lastTs=Long.MIN_VALUE;
                for(C c:out){ if(c.t!=lastTs){ unique.add(c); lastTs=c.t; } }
                out=unique;
                if(out.size()>2 && now-out.get(out.size()-1).t<sec) out.remove(out.size()-1);
                if(out.size()>=80) return out;
            }catch(Exception e){ last=e; }
            out.clear();
            try{Thread.sleep(350);}catch(InterruptedException ignored){}
        }
        throw new Exception("Недостаточно закрытых свечей: "+interval+" (KuCoin вернул мало данных; повторите анализ через несколько секунд)"+(last==null?"":" — "+last.getMessage()));
    }

    private MarketExtras getExtras(String s)throws Exception{
        double bid=0,ask=0,oi=Double.NaN,prevOi=Double.NaN,funding=Double.NaN,index=Double.NaN,mark=Double.NaN;
        try{
            JSONObject j=getJson(API+"orderbook?tradeType=FUTURES&symbol="+URLEncoder.encode(s,"UTF-8")+"&limit=20");
            JSONObject d=j.optJSONObject("data"); bid=sideSum(d==null?null:d.optJSONArray("bids")); ask=sideSum(d==null?null:d.optJSONArray("asks"));
        }catch(Exception ignored){}
        try{
            JSONObject j=getJson(API+"open-interest?symbol="+URLEncoder.encode(s,"UTF-8")+"&interval=5min&pageSize=7");
            JSONArray a=j.optJSONArray("data");
            if(a!=null&&a.length()>0){
                ArrayList<double[]> pts=new ArrayList<>();
                for(int i=0;i<a.length();i++){ JSONObject o=a.getJSONObject(i); double v=number(o,"openInterest"); long ts=o.optLong("ts",0); if(!Double.isNaN(v)&&ts>0)pts.add(new double[]{ts,v}); }
                Collections.sort(pts,Comparator.comparingDouble(x->x[0]));
                if(!pts.isEmpty()){ oi=pts.get(pts.size()-1)[1]; prevOi=pts.get(Math.max(0,pts.size()-7))[1]; }
            }
        }catch(Exception ignored){}
        try{
            JSONObject j=getJson(API+"funding-rate?symbol="+URLEncoder.encode(s,"UTF-8"));
            JSONObject d=j.optJSONObject("data"); if(d!=null) funding=number(d,"nextFundingRate");
        }catch(Exception ignored){}
        try{
            JSONObject j=getJson(API+"ticker?tradeType=FUTURES&symbol="+URLEncoder.encode(s,"UTF-8"));
            JSONObject d=j.optJSONObject("data"); JSONArray a=d==null?null:d.optJSONArray("list");
            if(a!=null&&a.length()>0){ JSONObject x=a.getJSONObject(0); index=number(x,"indexPrice"); mark=number(x,"markPrice"); }
        }catch(Exception ignored){}
        return new MarketExtras(bid,ask,oi,prevOi,funding,index,mark);
    }
    private double number(JSONObject o,String key){ Object v=o.opt(key); if(v==null||v==JSONObject.NULL)return Double.NaN; try{return Double.parseDouble(String.valueOf(v));}catch(Exception e){return Double.NaN;} }
    private double sideSum(JSONArray a){ double x=0; if(a==null)return 0; for(int i=0;i<Math.min(20,a.length());i++){try{x+=Double.parseDouble(String.valueOf(a.getJSONArray(i).get(1)));}catch(Exception ignored){}} return x; }
    private JSONObject getJson(String u)throws Exception{
        Exception last=null;
        for(int attempt=0;attempt<3;attempt++){
            HttpURLConnection x=null;
            try{
                x=(HttpURLConnection)new URL(u).openConnection(); x.setConnectTimeout(8000); x.setReadTimeout(12000); x.setRequestMethod("GET");
                int code=x.getResponseCode(); String body=readAll(code>=200&&code<300?x.getInputStream():x.getErrorStream());
                if(code<200||code>=300) throw new Exception("HTTP "+code);
                JSONObject j=new JSONObject(body); if(!"200000".equals(j.optString("code"))) throw new Exception("KuCoin: "+j.optString("msg","API error")); return j;
            }catch(Exception e){last=e; try{Thread.sleep(250L*(attempt+1));}catch(InterruptedException ignored){}}
            finally{if(x!=null)x.disconnect();}
        }
        throw last==null?new Exception("API error"):last;
    }
    private static String readAll(InputStream in)throws IOException{ if(in==null)return""; try(InputStream x=in;ByteArrayOutputStream b=new ByteArrayOutputStream()){byte[] z=new byte[4096];int n;while((n=x.read(z))!=-1)b.write(z,0,n);return b.toString(StandardCharsets.UTF_8.name());} }

    private double ema(ArrayList<C> c,int n){ return emaAt(c,n,c.size()-1); }
    private double emaAt(ArrayList<C> c,int n,int end){ if(end<0)return Double.NaN; int st=Math.max(0,end-n*4); double a=2.0/(n+1),v=c.get(st).cl; for(int i=st+1;i<=end;i++)v=a*c.get(i).cl+(1-a)*v; return v; }
    private double atrAt(ArrayList<C> c,int n,int end){ if(end<n)return Double.NaN; double s=0; int st=Math.max(1,end-n+1); for(int i=st;i<=end;i++){C x=c.get(i),p=c.get(i-1);s+=Math.max(x.h-x.l,Math.max(Math.abs(x.h-p.cl),Math.abs(x.l-p.cl)));} return s/(end-st+1); }
    private double atr(ArrayList<C> c,int n){return atrAt(c,n,c.size()-1);}
    private double rsi(ArrayList<C> c,int n){ if(c.size()<n+1)return 50; double gain=0,loss=0; int st=c.size()-n; for(int i=st;i<c.size();i++){double d=c.get(i).cl-c.get(i-1).cl;if(d>0)gain+=d;else loss-=d;} if(loss==0)return gain==0?50:100; double rs=gain/loss; return 100-100/(1+rs); }
    private double rsiAt(ArrayList<C> c,int n,int end){ if(end<n)return 50; double gain=0,loss=0; int st=end-n+1; for(int i=st;i<=end;i++){double d=c.get(i).cl-c.get(i-1).cl;if(d>0)gain+=d;else loss-=d;} if(loss==0)return gain==0?50:100; return 100-100/(1+gain/loss); }
    private double macdHist(ArrayList<C> c){return macdHistAt(c,c.size()-1);}
    private double macdHistAt(ArrayList<C> c,int end){ int st=Math.max(0,end-120); double a12=2.0/13.0,a26=2.0/27.0,e12=c.get(st).cl,e26=c.get(st).cl; ArrayList<Double> m=new ArrayList<>(); for(int i=st+1;i<=end;i++){e12=a12*c.get(i).cl+(1-a12)*e12;e26=a26*c.get(i).cl+(1-a26)*e26;m.add(e12-e26);} if(m.size()<9)return m.isEmpty()?0:m.get(m.size()-1); double a9=0.2,s=m.get(0);for(int i=1;i<m.size();i++)s=a9*m.get(i)+(1-a9)*s;return m.get(m.size()-1)-s; }
    private double[] diAdx(ArrayList<C> c,int n){
        if(c.size()<n*2+2)return new double[]{0,0,0};
        ArrayList<Double> tr=new ArrayList<>(),plus=new ArrayList<>(),minus=new ArrayList<>();
        for(int i=1;i<c.size();i++){C x=c.get(i),p=c.get(i-1);double range=Math.max(x.h-x.l,Math.max(Math.abs(x.h-p.cl),Math.abs(x.l-p.cl)));double up=x.h-p.h,down=p.l-x.l;tr.add(range);plus.add(up>down&&up>0?up:0);minus.add(down>up&&down>0?down:0);}
        double at=0,pdm=0,mdm=0;for(int i=0;i<n;i++){at+=tr.get(i);pdm+=plus.get(i);mdm+=minus.get(i);}at/=n;pdm/=n;mdm/=n;ArrayList<Double> dx=new ArrayList<>();double pdi=0,mdi=0;
        for(int i=n;i<tr.size();i++){at=((at*(n-1))+tr.get(i))/n;pdm=((pdm*(n-1))+plus.get(i))/n;mdm=((mdm*(n-1))+minus.get(i))/n;pdi=at==0?0:100*pdm/at;mdi=at==0?0:100*mdm/at;dx.add(100*Math.abs(pdi-mdi)/Math.max(.0001,pdi+mdi));}
        if(dx.size()<n)return new double[]{dx.isEmpty()?0:dx.get(dx.size()-1),pdi,mdi};double ad=0;for(int i=0;i<n;i++)ad+=dx.get(i);ad/=n;for(int i=n;i<dx.size();i++)ad=((ad*(n-1))+dx.get(i))/n;return new double[]{ad,pdi,mdi};
    }
    private double adx(ArrayList<C> c,int n){return diAdx(c,n)[0];}
    private double avgVol(ArrayList<C> c,int n){int e=c.size()-1,st=Math.max(0,e-n);double s=0;for(int i=st;i<e;i++)s+=c.get(i).vol;return s/Math.max(1,e-st);}
    private double highest(ArrayList<C> c,int n){double x=-Double.MAX_VALUE;for(int i=Math.max(0,c.size()-n);i<c.size();i++)x=Math.max(x,c.get(i).h);return x;}
    private double lowest(ArrayList<C> c,int n){double x=Double.MAX_VALUE;for(int i=Math.max(0,c.size()-n);i<c.size();i++)x=Math.min(x,c.get(i).l);return x;}
    private double vwap(ArrayList<C> c,int n){int st=Math.max(0,c.size()-n);double pv=0,v=0;for(int i=st;i<c.size();i++){C x=c.get(i);double tp=(x.h+x.l+x.cl)/3.0;pv+=tp*x.vol;v+=x.vol;}return v==0?c.get(c.size()-1).cl:pv/v;}
    private double bbPos(ArrayList<C> c,int n){int st=Math.max(0,c.size()-n);double m=0;for(int i=st;i<c.size();i++)m+=c.get(i).cl;m/=c.size()-st;double q=0;for(int i=st;i<c.size();i++){double d=c.get(i).cl-m;q+=d*d;}double sd=Math.sqrt(q/Math.max(1,c.size()-st));double up=m+2*sd,lo=m-2*sd,p=c.get(c.size()-1).cl;return (p-lo)/Math.max(1e-9,up-lo);}
    private int clamp(int x){return Math.max(0,Math.min(100,x));}

    private Bias bias(ArrayList<C> c){
        double p=c.get(c.size()-1).cl,e20=ema(c,20),e50=ema(c,50),e200=ema(c,Math.min(200,c.size())),r=rsi(c,14),a=atr(c,14),ad=adx(c,14),mh=macdHist(c);double[] di=diAdx(c,14);int l=0,s=0;
        if(p>e20)l+=2;else s+=2;if(e20>e50)l+=3;else s+=3;if(p>e200)l+=3;else s+=3;if(r>55)l+=2;else if(r<45)s+=2;if(mh>0)l+=2;else if(mh<0)s+=2;if(ad>=20){if(di[1]>di[2])l+=2;else if(di[2]>di[1])s+=2;}return new Bias(l,s,r,a,ad,e20,e50,e200,di[1],di[2],bbPos(c,20),vwap(c,50));
    }

    private double regimeHit(ArrayList<C> c, boolean longSide){
        int total=0,hit=0; int start=Math.max(55,c.size()-110), end=c.size()-4;
        for(int i=start;i<=end;i++){
            double e20=emaAt(c,20,i),e50=emaAt(c,50,i),r=rsiAt(c,14,i),ret=(c.get(i+3).cl-c.get(i).cl)/Math.max(1e-9,c.get(i).cl);
            boolean cond=longSide ? e20>e50&&r>52 : e20<e50&&r<48;
            if(cond){total++; if(longSide?ret>0:ret<0)hit++;}
        }
        return total<8?50.0:100.0*hit/total;
    }

    private Result analyze(Map<String,ArrayList<C>> d,MarketExtras ex){
        Bias b5=bias(d.get("5min")),b15=bias(d.get("15min")),b1=bias(d.get("1hour")),b4=bias(d.get("4hour")),bD=bias(d.get("1day"));
        int L=bD.l*6+b4.l*5+b1.l*4+b15.l*3+b5.l*2, S=bD.s*6+b4.s*5+b1.s*4+b15.s*3+b5.s*2;
        ArrayList<C> c5=d.get("5min"),c15=d.get("15min"),c1=d.get("1hour"),c4=d.get("4hour"),cd=d.get("1day");C z=c5.get(c5.size()-1),p=c5.get(c5.size()-2);double av=avgVol(c5,20),vr=av==0?1:z.vol/av;
        if(vr>=1.5){if(z.cl>p.cl)L+=7;else if(z.cl<p.cl)S+=7;}
        double r15h=highest(c15,30),r15l=lowest(c15,30),r1h=highest(c1,30),r1l=lowest(c1,30),price=z.cl;
        if(price>=r15h*.999)L+=6;if(price<=r15l*1.001)S+=6;if(price>=r1h*.999)L+=5;if(price<=r1l*1.001)S+=5;
        double imb=(ex.bid+ex.ask)==0?0:(ex.bid-ex.ask)/(ex.bid+ex.ask);if(imb>.15)L+=5;else if(imb<-.15)S+=5;
        double oiDelta=Double.NaN;if(!Double.isNaN(ex.oi)&&!Double.isNaN(ex.prevOi)&&ex.prevOi!=0)oiDelta=(ex.oi-ex.prevOi)/ex.prevOi;int ref=Math.max(0,c5.size()-7);double priceDelta=(z.cl-c5.get(ref).cl)/Math.max(1e-9,c5.get(ref).cl);
        if(!Double.isNaN(oiDelta)&&Math.abs(oiDelta)>=.001){if(priceDelta>0&&oiDelta>0)L+=6;else if(priceDelta<0&&oiDelta>0)S+=6;else if(priceDelta>0&&oiDelta<0)L+=2;else if(priceDelta<0&&oiDelta<0)S+=2;}
        if(!Double.isNaN(ex.funding)){if(ex.funding>.0015)S+=3;else if(ex.funding<-.0015)L+=3;}
        double premium=(!Double.isNaN(ex.mark)&&!Double.isNaN(ex.index)&&ex.index!=0)?(ex.mark-ex.index)/ex.index:0;
        if(Math.abs(premium)>.0005){if(premium>0)S+=2;else L+=2;}
        double vwap=vwap(c5,50),bb=bbPos(c5,20),atrPct=atr(c1,14)/Math.max(1e-9,c1.get(c1.size()-1).cl),dSupport=(price-lowest(c15,30))/Math.max(1e-9,price),dRes=(highest(c15,30)-price)/Math.max(1e-9,price);
        if(price>vwap)L+=3;else S+=3;if(bb>.8&&price>vwap)L+=2;else if(bb<.2&&price<vwap)S+=2;
        double hitL=regimeHit(c1,true),hitS=regimeHit(c1,false);if(hitL>=60)L+=4;if(hitS>=60)S+=4;
        int max=Math.max(L,S),min=Math.min(L,S),raw=clamp((int)Math.round(max*100.0/155.0));
        boolean alignLong=bD.l>=8&&b4.l>=8&&b1.l>=8,alignShort=bD.s>=8&&b4.s>=8&&b1.s>=8,aligned=alignLong||alignShort,strong=max-min>=14;
        boolean tooCloseLong=dRes<Math.max(.003,atrPct*1.2),tooCloseShort=dSupport<Math.max(.003,atrPct*1.2);
        boolean enoughData=ex.bid+ex.ask>0&&!Double.isNaN(oiDelta)&&!Double.isNaN(ex.funding)&&!Double.isNaN(ex.index)&&!Double.isNaN(ex.mark);
        String dir="WAIT";if(raw>=72&&strong&&aligned&&enoughData){if(L>S&&!tooCloseLong)dir="LONG";else if(S>L&&!tooCloseShort)dir="SHORT";}
        double atr=Math.max(b5.a,b15.a*.7),entry=price,sl,tp1,tp2,tp3,swingL=lowest(c15,20),swingH=highest(c15,20);
        if(dir.equals("LONG")){sl=Math.min(swingL,entry-1.5*atr);if(sl>=entry)sl=entry-1.5*atr;double risk=entry-sl;tp1=entry+1.2*risk;tp2=entry+2*risk;tp3=entry+3*risk;}
        else if(dir.equals("SHORT")){sl=Math.max(swingH,entry+1.5*atr);if(sl<=entry)sl=entry+1.5*atr;double risk=sl-entry;tp1=entry-1.2*risk;tp2=entry-2*risk;tp3=entry-3*risk;}
        else sl=tp1=tp2=tp3=Double.NaN;
        return new Result(dir,raw,L,S,entry,sl,tp1,tp2,tp3,b5,b15,b1,b4,bD,vr,imb,ex.funding,oiDelta,premium,vwap,bb,hitL,hitS,atrPct,tooCloseLong,tooCloseShort,enoughData);
    }

    private String priceFmt(double v){if(Double.isNaN(v))return"—";if(Math.abs(v)>=1000)return String.format(Locale.US,"%.1f",v);if(Math.abs(v)>=1)return String.format(Locale.US,"%.2f",v);return String.format(Locale.US,"%.6f",v);}
    private void show(Result r){
        String candidate=r.l>r.s?"LONG":r.s>r.l?"SHORT":"НЕЙТРАЛЬНО";boolean longAlign=r.bD.l>=8&&r.b4.l>=8&&r.b1.l>=8,shortAlign=r.bD.s>=8&&r.b4.s>=8&&r.b1.s>=8;boolean ready=!r.d.equals("WAIT");
        signal.setText(ready?r.d+"  "+r.score+"/100":"ОЖИДАНИЕ  •  "+candidate+"  "+r.score+"/100");
        StringBuilder e=new StringBuilder();
        if(!ready){e.append("ВХОДА НЕТ — ОЖИДАНИЕ\n\nНаправление: ").append(candidate).append("\nОценка подтверждения: ").append(r.score).append("/100\n\nВХОД ЗАБЛОКИРОВАН: ");
            if(!r.enoughData)e.append("НЕ ПОЛУЧЕНЫ КРИТИЧЕСКИЕ ДАННЫЕ");else if(!(longAlign||shortAlign))e.append("1D/4Ч/1Ч НЕ СОГЛАСОВАНЫ");else if(Math.abs(r.l-r.s)<14)e.append("СЛИШКОМ МАЛАЯ РАЗНИЦА LONG/SHORT");else if((candidate.equals("LONG")&&r.tooCloseLong)||(candidate.equals("SHORT")&&r.tooCloseShort))e.append("СЛИШКОМ БЛИЗКО ПРОТИВОПОЛОЖНЫЙ УРОВЕНЬ");else e.append("НЕ ВСЕ ФИЛЬТРЫ ПОДТВЕРЖДАЮТ ВХОД");e.append("\n\n");}
        else e.append("Вход: ").append(priceFmt(r.p)).append("\nСтоп-лосс: ").append(priceFmt(r.sl)).append("\nТейк-профит 1: ").append(priceFmt(r.tp1)).append("\nТейк-профит 2: ").append(priceFmt(r.tp2)).append("\nТейк-профит 3: ").append(priceFmt(r.tp3)).append("\n\n");
        String oi=Double.isNaN(r.oiDelta)?"N/A":String.format(Locale.US,"%+.2f%%",r.oiDelta*100);String f=Double.isNaN(r.funding)?"N/A":String.format(Locale.US,"%.5f%%",r.funding*100);String prem=String.format(Locale.US,"%+.3f%%",r.premium*100);
        details.setText(e.toString()+String.format(Locale.US,
            "LONG: %d   SHORT: %d\n"+
            "1D: %s  (L%d / S%d)\n4Ч: %s  (L%d / S%d)\n1Ч: %s  (L%d / S%d)\n"+
            "RSI 5м/15м/1ч/4ч/1D: %.1f / %.1f / %.1f / %.1f / %.1f\n"+
            "ADX 1Ч: %.1f  +DI %.1f  -DI %.1f\n"+
            "VWAP 5м: %s  •  BB %s\n"+
            "Объём / средний: %.2f\nДисбаланс стакана: %+.2f\n"+
            "Изменение OI ~30 мин: %s\nФандинг: %s\nMark-Index: %s\n"+
            "Историческая устойчивость 1Ч: LONG %.0f%% / SHORT %.0f%%\n"+
            "ATR 1Ч / цена: %.2f%%\n\n"+
            "Фильтры: EMA20/50/200 • RSI • MACD • ADX/DI • VWAP • Bollinger • структура • объём • стакан • OI • funding • mark/index",
            r.l,r.s,longAlign?"LONG ✓":shortAlign?"SHORT ✓":"ДРУГОЕ",r.bD.l,r.bD.s,longAlign?"LONG ✓":shortAlign?"SHORT ✓":"ДРУГОЕ",r.b4.l,r.b4.s,longAlign?"LONG ✓":shortAlign?"SHORT ✓":"ДРУГОЕ",r.b1.l,r.b1.s,
            r.b5.rsi,r.b15.rsi,r.b1.rsi,r.b4.rsi,r.bD.rsi,r.b1.adx,r.b1.plusDi,r.b1.minusDi,priceFmt(r.vwap),String.format(Locale.US,"%.2f",r.bb),r.vr,r.imb,oi,f,prem,r.hitL,r.hitS,r.atrPct*100));
        status.setText("Обновлено: "+new Date()+" • закрытые свечи • вход только при согласовании 1D+4Ч+1Ч • без гарантии результата");
    }

    static class C{long t;double o,h,l,cl,vol;C(long t,double o,double h,double l,double c,double v){this.t=t;this.o=o;this.h=h;this.l=l;cl=c;vol=v;}}
    static class Bias{int l,s;double rsi,a,adx,e20,e50,e200,plusDi,minusDi,bb,vwap;Bias(int l,int s,double r,double a,double ad,double e20,double e50,double e200,double p,double m,double bb,double v){this.l=l;this.s=s;rsi=r;this.a=a;adx=ad;this.e20=e20;this.e50=e50;this.e200=e200;plusDi=p;minusDi=m;this.bb=bb;vwap=v;}}
    static class MarketExtras{double bid,ask,oi,prevOi,funding,index,mark;MarketExtras(double b,double a,double oi,double prev,double f,double i,double m){bid=b;ask=a;this.oi=oi;prevOi=prev;funding=f;index=i;mark=m;}double oiDelta(){return oi;}}
    static class Result{String d;int score,l,s;double p,sl,tp1,tp2,tp3,vr,imb,funding,oiDelta,premium,vwap,bb,hitL,hitS,atrPct;Bias b5,b15,b1,b4,bD;boolean tooCloseLong,tooCloseShort,enoughData;Result(String d,int sc,int l,int s,double p,double sl,double a,double b,double c,Bias b5,Bias b15,Bias b1,Bias b4,Bias bD,double vr,double imb,double f,double oi,double prem,double vwap,double bb,double hl,double hs,double ap,boolean cl,boolean cs,boolean ed){this.d=d;score=sc;this.l=l;this.s=s;this.p=p;this.sl=sl;tp1=a;tp2=b;tp3=c;this.b5=b5;this.b15=b15;this.b1=b1;this.b4=b4;this.bD=bD;this.vr=vr;this.imb=imb;funding=f;oiDelta=oi;premium=prem;this.vwap=vwap;this.bb=bb;hitL=hl;hitS=hs;atrPct=ap;tooCloseLong=cl;tooCloseShort=cs;enoughData=ed;}}
}
