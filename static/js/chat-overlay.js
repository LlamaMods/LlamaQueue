(() => {
    const list = document.getElementById('chat-message-list');
    const token = list?.dataset.overlayToken;
    if (!list || !token) return;
    const defaults = {theme:'transparent',fontSize:16,fontFamily:'Arial, sans-serif',backgroundColor:'#111820',backgroundOpacity:78,textColor:'#f3f5f7',usernameColor:'#ffffff',twitchColor:'#9146ff',youtubeColor:'#e62117',showPlatform:true,showTimestamp:true,showUsername:true,showBadges:true,maxMessages:30,messageSpacing:7,messageRadius:8};
    let appearance = {...defaults};
    try { const node=document.getElementById('chat-appearance-json'); if(node) appearance={...defaults,...JSON.parse(node.textContent)}; } catch (_) {}
    const root=document.documentElement;
    root.style.setProperty('--chat-font',appearance.fontFamily);
    root.style.setProperty('--chat-font-size',`${appearance.fontSize}px`);
    root.style.setProperty('--chat-text',appearance.textColor);
    root.style.setProperty('--chat-username',appearance.usernameColor);
    root.style.setProperty('--chat-twitch',appearance.twitchColor);
    root.style.setProperty('--chat-youtube',appearance.youtubeColor);
    root.style.setProperty('--chat-spacing',`${appearance.messageSpacing}px`);
    root.style.setProperty('--chat-radius',`${appearance.messageRadius}px`);
    const alpha=Math.round(appearance.backgroundOpacity*2.55).toString(16).padStart(2,'0');
    root.style.setProperty('--chat-bubble',appearance.theme==='transparent'?`${appearance.backgroundColor}${alpha}`:appearance.theme==='light'?'rgba(255,255,255,.88)':'rgba(10,14,20,.94)');
    document.body.classList.toggle('chat-theme-light',appearance.theme==='light');
    document.body.classList.toggle('chat-theme-dark',appearance.theme==='dark');
    document.body.classList.toggle('chat-hide-platform',!appearance.showPlatform);
    document.body.classList.toggle('chat-hide-time',!appearance.showTimestamp);
    document.body.classList.toggle('chat-hide-user',!appearance.showUsername);
    const seen=new Set();
    const OBS_SEEN_LIMIT=600;
    let empty=document.getElementById('chat-empty');
    function addMessage(message){
        if(!message||!message.text)return;
        const key=`${message.platform}:${message.id||`${message.username}:${message.timestamp}:${message.text}`}`;
        if(seen.has(key))return; seen.add(key);
        while(seen.size>OBS_SEEN_LIMIT)seen.delete(seen.values().next().value);
        const createdAt = new Date(message.timestamp || Date.now()).getTime();
        const age = Math.max(0, Date.now() - (Number.isFinite(createdAt) ? createdAt : Date.now()));
        const visibleFor = 24000;
        const fadeFor = 6000;
        if (age >= visibleFor + fadeFor) return;
        empty?.remove();empty=null;
        const row=document.createElement('div');row.className='chat-message';
        const badge=document.createElement('span');badge.className=`chat-message-platform ${message.platform}`;badge.textContent=message.platform==='twitch'?'T':'▶';
        const content=document.createElement('div');content.className='chat-message-content';
        const meta=document.createElement('div');meta.className='chat-message-meta';
        const user=document.createElement('span');user.className='chat-message-user';user.textContent=message.username||'Viewer';
        const badgeItems=Array.isArray(message.badge_items)?message.badge_items:(message.badge_icons||[]).map(url=>({url,title:'Twitch badge'}));
        const time=document.createElement('span');time.className='chat-message-time';const date=new Date(message.timestamp||Date.now());time.textContent=Number.isNaN(date.getTime())?'':date.toLocaleTimeString([],{hour:'numeric',minute:'2-digit'});
        const text=document.createElement('div');text.className='chat-message-text';text.textContent=message.text;
        meta.append(user);
        if(appearance.showBadges){
            if(message.subscription_badge){const subTag=document.createElement('span');subTag.className='chat-user-badge chat-subscription-badge';subTag.textContent=String(message.subscription_badge).slice(0,12);subTag.title='Subscription tier';meta.append(subTag);}
            if(message.tenure_badge){const tenureTag=document.createElement('span');tenureTag.className='chat-user-badge chat-tenure-badge';tenureTag.textContent=String(message.tenure_badge).slice(0,8);tenureTag.title='Subscription tenure';meta.append(tenureTag);}
            if(message.platform==='twitch'){
                badgeItems.slice(0,8).forEach(item=>{
                    const src=typeof item==='string'?item:item?.url;
                    const label=String((typeof item==='object'&&(item.title||item.set_id))||'Platform badge').replace(/_/g,' ').replace(/\s+/g,' ').trim();
                    if(/^https:\/\//i.test(String(src||''))){const icon=document.createElement('img');icon.className='chat-platform-badge-icon';icon.src=src;icon.alt=label;icon.title=label;icon.loading='lazy';icon.addEventListener('error',()=>{const tag=document.createElement('span');tag.className='chat-user-badge';tag.textContent=label;icon.replaceWith(tag);},{once:true});meta.append(icon);}
                    else if(label!=='Platform badge'){const tag=document.createElement('span');tag.className='chat-user-badge';tag.textContent=label;meta.append(tag);}
                });
            }else{
                const labels=[...(message.badges||[])];if(message.verified)labels.push('Verified');if(message.moderator)labels.push('Moderator');if(message.owner)labels.push('Owner');
                labels.filter(label=>! /^(owner|moderator)$/i.test(String(label))).slice(0,5).forEach(label=>{const tag=document.createElement('span');tag.className='chat-user-badge';tag.textContent=String(label).replace(/[^a-z0-9 _-]/gi,'').slice(0,24);meta.append(tag);});
            }
        }
        meta.append(time);content.append(meta,text);row.append(badge,content);list.append(row);
        // OBS has less vertical room than the dashboard: cap it at eight rows.
        while(list.querySelectorAll('.chat-message').length>appearance.maxMessages){
            list.querySelector('.chat-message')?.remove();
        }
        // OBS-only lifecycle: each message gets its own 24s hold and 6s fade.
        const holdRemaining = Math.max(0, visibleFor - age);
        const fadeRemaining = Math.max(0, fadeFor - Math.max(0, age - visibleFor));
        window.setTimeout(() => {
            if (!row.isConnected) return;
            row.style.transitionDuration = `${fadeRemaining}ms`;
            row.classList.add('chat-overlay-message-fading');
            window.setTimeout(() => row.remove(), fadeRemaining);
        }, holdRemaining);
    }
    const protocol=location.protocol==='https:'?'wss:':'ws:';
    const socket=new WebSocket(`${protocol}//${location.host}/chat/overlay/ws/${encodeURIComponent(token)}`);
    socket.addEventListener('open',()=>socket.send('ready'));
    socket.addEventListener('message',event=>{const data=JSON.parse(event.data);if(data.type==='snapshot')(data.messages||[]).forEach(addMessage);else if(data.type==='message')addMessage(data.message);});
    const heartbeat=setInterval(()=>{if(socket.readyState===WebSocket.OPEN)socket.send('ping');},20000);
    window.addEventListener('beforeunload',()=>{clearInterval(heartbeat);socket.close();});
})();