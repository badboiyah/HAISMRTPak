'use strict';
// Supply Vietnamese validation even when the browser's own language is English.
window.vietnameseError = error => {
  if (error.name === 'TimeoutError' || error.name === 'AbortError') return 'Kết nối quá thời gian chờ. Vui lòng thử lại.';
  if (error instanceof TypeError) return 'Không thể kết nối máy chủ. Vui lòng kiểm tra mạng và thử lại.';
  if (error instanceof SyntaxError) return 'Máy chủ trả về dữ liệu không hợp lệ. Vui lòng thử lại.';
  return error.message || 'Không thể xử lý yêu cầu. Vui lòng thử lại.';
};
document.addEventListener('invalid', event => {
  const field = event.target;
  if (!(field instanceof HTMLInputElement) && !(field instanceof HTMLSelectElement)) return;
  field.setCustomValidity('');
  const v = field.validity;
  let message = 'Giá trị chưa hợp lệ. Vui lòng kiểm tra lại.';
  if (v.valueMissing) message = 'Vui lòng điền thông tin này.';
  else if (v.typeMismatch && field.type === 'email') message = 'Vui lòng nhập địa chỉ thư điện tử hợp lệ.';
  else if (v.tooShort) message = `Vui lòng nhập ít nhất ${field.minLength} ký tự.`;
  else if (v.tooLong) message = `Vui lòng nhập tối đa ${field.maxLength} ký tự.`;
  else if (v.rangeUnderflow) message = `Giá trị phải lớn hơn hoặc bằng ${field.min}.`;
  else if (v.rangeOverflow) message = `Giá trị phải nhỏ hơn hoặc bằng ${field.max}.`;
  else if (v.badInput || v.stepMismatch) message = 'Vui lòng nhập một số hợp lệ.';
  field.setCustomValidity(message);
}, true);
for (const name of ['input', 'change']) document.addEventListener(name, event => {
  if (typeof event.target.setCustomValidity === 'function') event.target.setCustomValidity('');
});
