// 页面逻辑
let ispSelect, cmccOptions, usernameInput, usernameLabel, accountPreview, passwordInput, passwordHint, togglePassword, form, resultBox, resultContent, logBox, toggleLog, nameInput, roleSelect, changePasswordBtn;

// 等待i18n初始化完成后再初始化页面
function initApp() {
  ispSelect = document.getElementById('isp');
  cmccOptions = document.getElementById('cmccOptions');
  usernameInput = document.getElementById('username');
  usernameLabel = document.getElementById('usernameLabel');
  accountPreview = document.getElementById('accountPreview');
  passwordInput = document.getElementById('password');
  passwordHint = document.getElementById('passwordHint');
  togglePassword = document.getElementById('togglePassword');
  form = document.getElementById('pppoeForm');
  resultBox = document.getElementById('resultBox');
  resultContent = document.getElementById('resultContent');
  logBox = document.getElementById('logBox');
  toggleLog = document.getElementById('toggleLog');
  nameInput = document.getElementById('name');
  roleSelect = document.getElementById('role');
  changePasswordBtn = document.getElementById('changePasswordBtn');
  
  // ISP切换
  ispSelect.addEventListener('change', () => {
    if (ispSelect.value === "cmccgx") {
      cmccOptions.classList.remove('hidden');
      usernameLabel.textContent = t('usernameLabelPhone');
      usernameInput.placeholder = t('usernamePlaceholderPhone');
      changePasswordBtn.style.display = 'block';
      changePasswordBtn.textContent = t('changePasswordButton');
    } else if (ispSelect.value === "cdu") {
      cmccOptions.classList.add('hidden');
      usernameLabel.textContent = t('usernameLabelStudent');
      usernameInput.placeholder = t('usernamePlaceholderStudent');
      changePasswordBtn.style.display = 'block';
      changePasswordBtn.textContent = t('changePasswordButton');
    } else if (ispSelect.value === "direct") {
      cmccOptions.classList.add('hidden');
      usernameLabel.textContent = t('usernameLabelDirect');
      usernameInput.placeholder = t('usernamePlaceholderDirect');
      changePasswordBtn.style.display = 'none';
    } else if (ispSelect.value === "10010") {
      cmccOptions.classList.add('hidden');
      usernameLabel.textContent = t('usernameLabelPhone');
      usernameInput.placeholder = t('usernamePlaceholderPhone');
      changePasswordBtn.style.display = 'block';
      changePasswordBtn.textContent = t('changePasswordButton');
    } else if (ispSelect.value === "96301") {
      cmccOptions.classList.add('hidden');
      usernameLabel.textContent = t('usernameLabelPhone');
      usernameInput.placeholder = t('usernamePlaceholderPhone');
      changePasswordBtn.style.display = 'block';
      changePasswordBtn.textContent = t('changePasswordButton');
    } else {
      cmccOptions.classList.add('hidden');
      usernameLabel.textContent = t('usernameLabelPhone');
      usernameInput.placeholder = t('usernamePlaceholderPhone');
      changePasswordBtn.style.display = 'none';
    }
    updatePreview();
    updatePasswordHint();
  });
  
  togglePassword.addEventListener('click', () => {
    if (passwordInput.type === "password") {
      passwordInput.type = "text";
      togglePassword.textContent = "🙈";
    } else {
      passwordInput.type = "password";
      togglePassword.textContent = "👁️";
    }
  });
  
  usernameInput.addEventListener('input', () => { updatePreview(); updatePasswordHint(); });
  document.querySelectorAll('input[name="cmccType"]').forEach(el => el.addEventListener('change', () => { updatePreview(); updatePasswordHint(); }));
  
  // 修改密码按钮点击事件
  changePasswordBtn.addEventListener('click', () => {
    const isp = ispSelect.value;
    
    if (isp === 'cdu') {
      window.open('https://id.cdu.edu.cn/login?service=https:%2F%2Fmyapp.cdu.edu.cn%2F', '_blank');
    } else if (isp === 'cmccgx') {
      alert(t('changePasswordCMCC'));
    } else if (isp === '10010') {
      alert(t('changePasswordUnicom'));
    } else if (isp === '96301') {
      alert(t('changePasswordTelecom'));
    }
  });
  
  // 表单提交
  form.addEventListener('submit', async (e) => {
    e.preventDefault();

    const submitBtn = document.getElementById('submitBtn');

    submitBtn.disabled = true;
    submitBtn.classList.add('loading');
    submitBtn.textContent = t('activatingButton');
    
    resultBox.classList.remove('hidden');
    resultContent.innerHTML = "<p class='info-text'>" + t('activating') + "</p>";
    
    const data = {
      username: usernameInput.value.trim(),
      password: passwordInput.value,
      name: nameInput.value.trim(),
      role: roleSelect.value,
      isp: ispSelect.value
    };
    
    if (!data.isp) {
      resultContent.innerHTML = "<p class='error'>❌ " + t('selectISP') + "</p>";
      submitBtn.disabled = false;
      submitBtn.textContent = t('activateButton');
      return;
    }
    
    if (data.isp === "cmccgx") {
      const cmccType = document.querySelector('input[name="cmccType"]:checked').value;
      if (cmccType === "scxy") data.username = "scxy" + data.username;
    }
    
    if (data.isp !== "direct") {
      const finalUsername = data.username + "@" + data.isp;
      data.username = finalUsername;
    }
    
    try {
      const res = await fetch('/activate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data)
      });
      const resp = await res.json();
      
      if (resp.success) {
        resultContent.innerHTML = `
          <p class="success">${t('successMessage')}</p>
          <p class="info-text">${t('accountLabel')}：${resp.username}</p>
          <p class="info-text">${t('ifaceLabel')}：${resp.iface}</p>
          <p class="info-text">${t('macLabel')}：${resp.mac}</p>
          <p class="info-text">${t('ipLabel')}：${resp.ip || '-'}</p>
        `;
      } else {
        const userTip = resp.error_message || window.errorMessages[resp.error_code] || "Unknown error";
        resultContent.innerHTML = `
          <p class="error">${t('errorMessage')}</p>
          <p class="info-text">${t('errorCodeLabel')}：${resp.error_code}</p>
          <p class="info-text">${t('tipLabel')}：${userTip}</p>
          <p class="info-text">${t('accountLabel')}：${resp.username}</p>
          <p class="info-text">${t('ifaceLabel')}：${resp.iface}</p>
        `;
      }
      
      logBox.textContent = resp.log || t('noLog');
    } catch (err) {
      resultContent.innerHTML = "<p class='error'>" + t('requestFailed') + "</p>";
    } finally {
      submitBtn.disabled = false;
      submitBtn.classList.remove('loading');
      submitBtn.textContent = t('activateButton');
    }
  });
  
  // 查看详细日志
  toggleLog.addEventListener('click', async () => {
    if (logBox.classList.contains('hidden')) {
      logBox.classList.remove('hidden');
      logBox.innerHTML = "<p class='log-loading'>" + t('loadingLog') + "</p>";
      
      try {
        const res = await fetch('/api/dial-logs');
        if (res.ok) {
          const data = await res.json();
          if (data.success && data.log_content) {
            logBox.textContent = `【${t('log_file') || '日志文件'}：${data.log_file}】\n\n${data.log_content}`;
          } else {
            logBox.textContent = data.error || (t('noLog') || "暂无日志记录");
          }
        } else {
          logBox.textContent = t('loadLogFailed');
        }
      } catch (err) {
        logBox.textContent = t('loadLogFailed');
      }
    } else {
      logBox.classList.add('hidden');
    }
  });
}

function updatePreview() {
  let baseUser = usernameInput.value.trim();
  const isp = ispSelect.value;
  
  if (!baseUser || !isp) {
    accountPreview.classList.add('hidden');
    return;
  }
  
  if (isp === "direct") {
    accountPreview.classList.add('hidden');
    return;
  }
  
  if (isp === "cmccgx") {
    const cmccType = document.querySelector('input[name="cmccType"]:checked')?.value;
    if (cmccType === "scxy") {
      baseUser = "scxy" + baseUser;
    }
  }
  
  const finalUsername = baseUser + "@" + isp;
  accountPreview.textContent = t('completeAccount') + finalUsername;
  accountPreview.classList.remove('hidden');
}

function updatePasswordHint() {
  const isp = ispSelect.value;
  const baseUser = usernameInput.value.trim();
  
  passwordInput.value = "";
  passwordHint.textContent = "";
  
  if (!isp) return;
  
  if (isp === "cdu") {
    passwordHint.textContent = t('passwordHintCDU');
  } else if (isp === "cmccgx") {
    const cmccType = document.querySelector('input[name="cmccType"]:checked')?.value;
    if (cmccType === "normal") {
      if (baseUser.length >= 6) passwordInput.value = baseUser.slice(-6);
      passwordHint.textContent = t('passwordHintCMCCNormal');
    } else {
      passwordHint.textContent = t('passwordHintCMCCModified');
    }
  } else if (isp === "96301") {
    if (baseUser.length >= 8) passwordInput.value = baseUser.slice(-8);
    passwordHint.textContent = t('passwordHintTelecom');
  } else if (isp === "10010") {
    passwordHint.textContent = t('passwordHintUnicom');
  } else if (isp === "direct") {
    passwordHint.textContent = t('passwordHintDirect');
  }
}

// 等待i18n初始化完成后再初始化页面
if (typeof window.initI18nDone === 'undefined') {
  // 如果i18n还没有初始化完成，等待初始化完成
  document.addEventListener('i18nReady', initApp);
} else {
  // 如果i18n已经初始化完成，直接初始化页面
  initApp();
}
