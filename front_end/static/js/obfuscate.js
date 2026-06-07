const fs = require('fs');
const cheerio = require('cheerio');
const JavaScriptObfuscator = require('javascript-obfuscator');

const htmlContent = fs.readFileSync('home.html', 'utf8');
const $ = cheerio.load(htmlContent);

// Target inline scripts
$('script').each((index, element) => {
    const scriptContent = $(element).html();
    
    // Ignore external scripts (src attributes) and empty tags
    if (scriptContent && scriptContent.trim() !== '') {
        const obfuscatedResult = JavaScriptObfuscator.obfuscate(scriptContent, {
            compact: true,
            controlFlowFlattening: true,
            stringArray: true,
            stringArrayEncoding: ['base64']
        });
        $(element).text(obfuscatedResult.getObfuscatedCode());
    }
});

fs.writeFileSync('home_obfuscated.html', $.html(), 'utf8');
