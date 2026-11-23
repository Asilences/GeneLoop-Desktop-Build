/* Auxiliary pages retain the final website direction and canonical home links. */
(()=>{
 document.documentElement.dataset.theme='lattice';
 document.querySelector('meta[name="theme-color"]').content='#fafbfb';
 const brand=document.querySelector('.site-banner .brand');
 if(brand&&!brand.querySelector('img')){const mark=document.createElement('img');mark.className='brand-mark';mark.alt='';mark.src='assets/brand/geneloop-mark.svg';brand.prepend(mark);}
 for(const link of document.querySelectorAll('a')){const href=link.getAttribute('href');if(href==='./')link.href='index.html';else if(href?.startsWith('./#'))link.href='index.html'+href.slice(2);}
})();
