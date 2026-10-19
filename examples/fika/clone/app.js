var n=document.getElementById('top');
addEventListener('scroll',function(){n.classList.toggle('sc',scrollY>10)});
document.getElementById('news-form').addEventListener('submit',function(e){e.preventDefault()});
