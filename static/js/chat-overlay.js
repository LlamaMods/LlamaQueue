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
    const seen=new Set(); let empty=document.getElementById('chat-empty');
    function addMessage(message){
        if(!message||!message.text)return;
        const key=`${message.platform}:${message.id||`${message.username}:${message.timestamp}:${message.text}`}`;
        if(seen.has(key))return; seen.add(key); if(seen.size>2000)seen.clear();
        empty?.remove();empty=null;
        const row=document.createElement('div');row.className='chat-message';
        const badge=document.createElement('span');badge.className=`chat-message-platform ${message.platform}`;badge.textContent=message.platform==='twitch'?'T':'▶';
        const content=document.createElement('div');content.className='chat-message-content';
        const meta=document.createElement('div');meta.className='chat-message-meta';
        const user=document.createElement('span');user.className='chat-message-user';user.textContent=message.username||'Viewer';
        const time=document.createElement('span');time.className='chat-message-time';const date=new Date(message.timestamp||Date.now());time.textContent=Number.isNaN(date.getTime())?'':date.toLocaleTimeString([],{hour:'numeric',minute:'2-digit'});
        const text=document.createElement('div');text.className='chat-message-text';text.textContent=message.text;
        meta.append(user);
        if(appearance.showBadges){
            if(message.subscription_badge){const subTag=document.createElement('span');subTag.className='chat-user-badge chat-subscription-badge';subTag.textContent=String(message.subscription_badge).slice(0,12);meta.append(subTag);}
            if(message.tenure_badge){const tenureTag=document.createElement('span');tenureTag.className='chat-user-badge chat-tenure-badge';tenureTag.textContent=String(message.tenure_badge).slice(0,8);meta.append(tenureTag);}
            const labels=[...(message.badges||[])];if(message.verified)labels.push('Verified');if(message.moderator)labels.push('Moderator');labels.slice(0,5).forEach(label=>{const tag=document.createElement('span');tag.className='chat-user-badge';tag.textContent=String(label).replace(/[^a-z0-9 _-]/gi,'').slice(0,24);meta.append(tag);});}
        meta.append(time);content.append(meta,text);row.append(badge,content);list.append(row);
        while(list.querySelectorAll('.chat-message').length>appearance.maxMessages)list.querySelector('.chat-message')?.remove();
    }
    const protocol=location.protocol==='https:'?'wss:':'ws:';
    const socket=new WebSocket(`${protocol}//${location.host}/chat/overlay/ws/${encodeURIComponent(token)}`);
    socket.addEventListener('open',()=>socket.send('ready'));
    socket.addEventListener('message',event=>{const data=JSON.parse(event.data);if(data.type==='snapshot')(data.messages||[]).slice(-appearance.maxMessages).forEach(addMessage);else if(data.type==='message')addMessage(data.message);});
    const heartbeat=setInterval(()=>{if(socket.readyState===WebSocket.OPEN)socket.send('ping');},20000);
    window.addEventListener('beforeunload',()=>{clearInterval(heartbeat);socket.close();});
})();