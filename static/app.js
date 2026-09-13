'use strict';
const $ = (selector) => document.querySelector(selector);
let csrf = '', state = null, view = 'overview', page = 1, pages = 1, timer = null, busy = false, lastStats = 0, modeDirty = false;
const labels = {overview:'Tổng quan', history:'Lịch sử hoạt động', analytics:'Thống kê', settings:'Thiết bị và cài đặt'};
const timeText = ts => ts ? new Date(ts*1000).toLocaleString('vi-VN', {timeZone:'Asia/Ho_Chi_Minh'}) : 'Chưa có dữ liệu';
const escapeHtml = str => String(str).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function toast(message, error=false) { const el=$('#toast'); el.textContent=message; el.classList.toggle('error',error); el.hidden=false; clearTimeout(timer); timer=setTimeout(()=>el.hidden=true,4500); }
async function api(path, data) {
  const response=await fetch('/api'+path,{method:data===undefined?'GET':'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:data===undefined?undefined:JSON.stringify(data),signal:AbortSignal.timeout(8000)});
  const result=await response.json();
  if(!response.ok){if(response.status===401 && path!='/login')showLogin();throw new Error(result.error||'Không thể xử lý yêu cầu.');}
  return result;
}
function showLogin(){csrf='';$('#login').hidden=false;$('#app').hidden=true;}
function showApp(){ $('#login').hidden=true;$('#app').hidden=false;$('#password').value='';refresh();}
$('#login-form').addEventListener('submit',async e=>{e.preventDefault();const button=e.submitter;button.disabled=true;try{csrf=(await api('/login',{password:$('#password').value})).csrf;$('#login-error').textContent='';showApp();}catch(err){$('#login-error').textContent=vietnameseError(err);}finally{button.disabled=false;}});
$('#logout').onclick=async()=>{try{await api('/logout',{});showLogin();}catch(e){toast(vietnameseError(e),true);}};
$('#mobile-logout').onclick=()=>$('#logout').click();
document.querySelectorAll('[data-view]').forEach(button=>button.onclick=()=>switchView(button.dataset.view));
function switchView(target){view=target;document.querySelectorAll('.view').forEach(el=>el.hidden=el.id!=='view-'+view);document.querySelectorAll('.nav-item').forEach(el=>el.classList.toggle('active',el.dataset.view===view));$('#breadcrumb').textContent=labels[view];refresh();}
function renderState(s){
  state=s;$('#free-count').textContent=String(s.available).padStart(2,'0');$('#occupied-count').textContent=String(s.occupied).padStart(2,'0');
  $('#free-caption').textContent=s.unknown?`${s.unknown} vị trí chưa xác định`:(s.full?'Bãi đã hết chỗ':'Sẵn sàng đón xe vào bãi');
  $('#occupancy-progress').style.width=(s.occupied/4*100)+'%';$('#occupancy-caption').textContent=`${s.occupied/4*100}% công suất sử dụng`;
  const connection=$('#connection');connection.hidden=s.mode==='simulation';connection.textContent=s.mode==='simulation'?'':s.online?'ESP32 trực tuyến':'ESP32 mất kết nối';connection.className='pill'+(s.online?'':' warning');
  const banner=$('#status-banner');banner.classList.toggle('alert',s.mode==='hardware'&&(!s.online||s.unknown>0));
  banner.hidden=s.mode==='simulation';banner.textContent=s.mode==='simulation'?'':!s.online?'ESP32 chưa kết nối hoặc đã ngừng gửi dữ liệu quá 15 giây. Trạng thái chỗ đỗ chưa xác định.':s.unknown?'Có cảm biến chưa xác định. Tạm dừng nhận xe vào cho đến khi đủ dữ liệu.':'◉  Đang nhận dữ liệu trực tiếp từ ESP32. Trang quản lý tự cập nhật mỗi 2 giây.';
  $('#slots').innerHTML=Object.entries(s.slots).map(([name,value])=>`<button class="slot ${value===true?'occupied':value===null?'unknown':''}" data-slot="${name}" ${s.mode!=='simulation'?'disabled':''} aria-label="${name}: ${value===true?'có xe':value===null?'chưa xác định':'trống'}${s.mode==='simulation'?', nhấn để đổi trạng thái':''}"><span class="slot-label">${name}</span>${value===true?'<img class="slot-car" src="/static/brand/parked-car.svg" alt="Ô tô đang đỗ">':`<span class="parking-p">${value===null?'?':'P'}</span>`}<span class="slot-status">${value===true?'Đang có xe':value===null?'Chưa xác định':'Còn trống'}</span></button>`).join('');
  $('#slots').querySelectorAll('button').forEach(b=>b.onclick=()=>mutate('/simulation',{slot:b.dataset.slot,occupied:s.slots[b.dataset.slot]!==true}));
  $('#updated-time').textContent=s.updated_at?'Cập nhật '+new Date(s.updated_at*1000).toLocaleTimeString('vi-VN'):'';
  $('#map-note').textContent=s.mode==='simulation'?'Nhấn vào vị trí để cập nhật trạng thái':'Dữ liệu cảm biến · Chu kỳ 2 giây';
  const pending=s.command&&s.command.expires_at>s.server_time;
  $('#gate-state').textContent=!s.online?'Chưa xác định':pending?'Đang chờ thiết bị':s.barrier==='open'?'Thanh chắn đang mở':'Thanh chắn đang đóng';
  $('#gate-state').className='pill '+(!s.online||pending?'warning':s.barrier==='open'?'':'neutral');$('#gate-arm').classList.toggle('open',s.online&&s.barrier==='open');
  $('#gate-note').textContent=s.beam?'Có vật cản tại cổng':s.pending_until>s.server_time?'Đang chờ xe vào vị trí':s.mode==='simulation'?'Điều khiển trên máy tính':'Trạng thái do ESP32 báo về';
  document.querySelectorAll('[data-gate]').forEach(b=>b.disabled=!s.online||!!pending||(b.dataset.gate==='entry'&&(s.unknown>0||s.full||s.barrier!=='closed'||s.pending_until>s.server_time))||(b.dataset.gate==='close'&&s.beam));
  if(!modeDirty)$('#mode-select').value=s.mode;
  $('#device-seen').textContent=timeText(s.last_seen);$('#beam-status').textContent=s.mode==='simulation'?'Không có vật cản':!s.online?'Chưa xác định':s.beam?'Có vật cản':'Không có vật cản';
}
async function mutate(path,data){if(busy)return;busy=true;try{const result=await api(path,data);if(path==='/mode')modeDirty=false;renderState(result);lastStats=0;await refresh();toast('Đã cập nhật hệ thống.');}catch(e){toast(vietnameseError(e),true);}finally{busy=false;}}
document.querySelectorAll('[data-gate]').forEach(b=>b.onclick=()=>mutate('/gate',{action:b.dataset.gate}));
function table(items){if(!items.length)return '<div class="empty"><strong>Chưa có hoạt động</strong>Các sự kiện sẽ xuất hiện khi cảm biến thay đổi hoặc có lệnh điều khiển.</div>';return `<div class="table-wrap"><table class="event-table"><thead><tr><th>HOẠT ĐỘNG</th><th>VỊ TRÍ</th><th>NGUỒN</th><th>THỜI GIAN</th></tr></thead><tbody>${items.map(e=>`<tr><td><span class="event-symbol">${e.kind==='occupied'?'↙':e.kind==='vacated'?'↗':'•'}</span>${escapeHtml(e.message.replace(/mô phỏng/gi,'cập nhật trên máy tính'))}</td><td>${escapeHtml(e.slot||'—')}</td><td><span class="source">${escapeHtml({simulation:'Máy tính',device:'ESP32',admin:'Quản trị'}[e.source]||e.source)}</span></td><td>${timeText(e.timestamp)}</td></tr>`).join('')}</tbody></table></div>`;}
function filterQuery(){return new URLSearchParams({page:String(page),date:$('#filter-date').value,kind:$('#filter-kind').value}).toString();}
async function loadHistory(){const result=await api('/events?'+filterQuery());pages=result.pages;$('#history-events').innerHTML=table(result.items);$('#page-info').textContent=`Trang ${page} / ${pages} · ${result.total} hoạt động`;$('#prev-page').disabled=page<=1;$('#next-page').disabled=page>=pages;}
async function loadStats(){const stats=await api('/stats');$('#today-count').textContent=String(stats.days.at(-1).arrivals).padStart(2,'0');$('#week-arrivals').textContent=stats.days.reduce((sum,d)=>sum+d.arrivals,0);$('#avg-duration').textContent=stats.average_minutes+' phút';const max=Math.max(1,...stats.days.flatMap(d=>[d.arrivals,d.departures]));$('#chart').innerHTML=stats.days.map(d=>`<div class="chart-group"><div class="bars"><div class="bar" role="img" aria-label="${d.date}: ${d.arrivals} lượt bắt đầu"><span>${d.arrivals}</span></div><div class="bar exit" role="img" aria-label="${d.date}: ${d.departures} lượt kết thúc"><span>${d.departures}</span></div></div><span class="chart-label">${d.date}</span></div>`).join('');$('#chart').querySelectorAll('.chart-group').forEach((group,i)=>{group.querySelector('.bar').style.height=stats.days[i].arrivals/max*100+'%';group.querySelector('.bar.exit').style.height=stats.days[i].departures/max*100+'%';});lastStats=Date.now();}
let refreshing=false;
async function refresh(){if(!csrf||refreshing)return;refreshing=true;try{renderState(await api('/state'));if(view==='overview')$('#recent-events').innerHTML=table((await api('/events')).items.slice(0,5));if(view==='history')await loadHistory();if(Date.now()-lastStats>10000)await loadStats();}catch(e){$('#connection').textContent='Mất kết nối máy chủ';$('#connection').className='pill warning';$('#status-banner').textContent='Không thể tải dữ liệu mới. Các số liệu đang hiển thị là dữ liệu cũ; điều khiển tạm khóa.';$('#status-banner').classList.add('alert');document.querySelectorAll('[data-gate], [data-slot]').forEach(b=>b.disabled=true);}finally{refreshing=false;}}
['#filter-date','#filter-kind'].forEach(id=>$(id).onchange=()=>{page=1;loadHistory().catch(e=>toast(vietnameseError(e),true));});
$('#clear-filter').onclick=()=>{$('#filter-date').value='';$('#filter-kind').value='';page=1;loadHistory().catch(e=>toast(vietnameseError(e),true));};
$('#prev-page').onclick=()=>{page--;loadHistory().catch(e=>toast(vietnameseError(e),true));};$('#next-page').onclick=()=>{page++;loadHistory().catch(e=>toast(vietnameseError(e),true));};
$('#export').onclick=()=>{window.location.href='/api/events/export?'+filterQuery();};
let selectedMode='';$('#mode-select').onchange=()=>{modeDirty=true;};$('#save-mode').onclick=()=>{selectedMode=$('#mode-select').value;if(selectedMode===state.mode){toast('Chế độ này đang được sử dụng.');return;}$('#mode-dialog').showModal();};$('#cancel-mode').onclick=()=>$('#mode-dialog').close();$('#confirm-mode').onclick=()=>{$('#mode-dialog').close();mutate('/mode',{mode:selectedMode});};
setInterval(()=>{$('#clock').textContent=new Date().toLocaleDateString('vi-VN',{day:'2-digit',month:'long',year:'numeric',timeZone:'Asia/Ho_Chi_Minh'});},1000);
setInterval(refresh,2000);
api('/session').then(result=>{csrf=result.csrf;showApp();}).catch(()=>showLogin());
